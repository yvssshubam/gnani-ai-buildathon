"""A caller who says the same thing again and again must reach a human quickly, never loop."""
import pytest

from app.dialogue import CallSession
from app.models import CallState, Extraction, Ticket


class _Store:
    def save(self, t):
        pass


class _FakeLLM:
    """Returns a fixed extraction per sentence: what a sensible LLM would give."""
    def __init__(self, table):
        self.table = table

    def extract(self, text, last_question, known):
        return Extraction(**self.table.get(text, {}))


def _call(lines, table, max_turns=12):
    t = Ticket(id="7001", caller_number="x")
    s = CallSession(t, _FakeLLM(table), _Store())
    actions = []
    for i, line in enumerate(lines * max_turns if len(lines) == 1 else lines):
        if i >= max_turns:
            break
        r = s.handle(line, "hi-IN")
        actions.append(r["action"])
        if r["done"] or r["waiting"]:     # handed over: the caller now waits in line for an officer
            break
    return t, actions


@pytest.mark.parametrize("name, line, extraction, by_turn", [
    ("panicking", "bachao bachao, paani aa gaya", dict(needs=["rescue"], panic="high"), 3),
    ("same fact again", "hum Velachery mein hain", dict(locality="Velachery"), 4),
    ("same question again", "boat kab aayegi?", dict(caller_question="when_help"), 4),
    ("nothing useful", "please please", dict(unclear=True), 4),
    ("don't know to everything", "pata nahi", dict(), 5),
    ("no to everything", "nahi", dict(unclear=True), 5),
])
def test_repeating_caller_is_handed_to_a_human(name, line, extraction, by_turn):
    t, actions = _call([line], {line: extraction})
    assert actions[-1] == "handoff", f"{name}: {actions}"
    assert len(actions) <= by_turn, f"{name}: took {len(actions)} turns: {actions}"
    assert t.call_state == CallState.HANDED_OFF


def test_one_question_then_real_answers_is_not_stuck():
    table = {"boat kab aayegi?": dict(caller_question="when_help"),
             "hum Velachery mein hain": dict(locality="Velachery", injured=False)}
    _, actions = _call(["boat kab aayegi?", "hum Velachery mein hain"], table)
    assert "handoff" not in actions


def test_one_dont_know_then_answers_completes_normally():
    first = "hum Velachery mein hain, koi ghayal nahi"
    lines = [first, "pata nahi", "pata nahi", "pehli", "teen log", "nahi", "ghutne tak", "haan sahi hai"]
    t, actions = _call(lines, {first: dict(locality="Velachery", injured=False)})
    assert actions[-1] == "close", actions
    assert t.call_state == CallState.COMPLETED