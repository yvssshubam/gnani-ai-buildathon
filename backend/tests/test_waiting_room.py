"""The waiting room (design v2, section 5), status questions (7.4) and the "one person" step (8.4).

The caller already holds a place in line for an officer; the AI runs alongside. Every line must be
true for that caller: P0/P1 stay on the line, P2/P3 are reviewed (no phone call promised).
"""
import pytest

from app import dialogue, phrases
from app.dialogue import CallSession, sounds_like_promise
from app.intents import ANGER, ASK_ROBOT, REFUSE_AI, REQUEST_HUMAN, STATUS_QUERY, detect
from app.models import Extraction, Ticket

LANGS = ("en-IN", "hi-IN", "te-IN", "ta-IN")


class _Store:
    def save(self, t):
        pass


class _LLM:
    def __init__(self, table):
        self.table = table

    def extract(self, text, last_question, known):
        return Extraction(**self.table.get(text, {}))


def session(table, greet=True):
    s = CallSession(Ticket(id="5101", caller_number="x"), _LLM(table), _Store())
    if greet:
        s.greeting()
    return s


@pytest.fixture(autouse=True)
def all_operators_busy(monkeypatch):
    monkeypatch.setattr(dialogue, "HUMAN_OPERATORS", 3)
    monkeypatch.setattr(dialogue, "HUMAN_OPERATORS_BUSY", 3)


# ---------------------------------------------------------------- intents by rule

@pytest.mark.parametrize("text, intent", [
    ("mujhe insaan se baat karni hai", REQUEST_HUMAN),
    ("मुझे किसी इंसान से बात करनी है", REQUEST_HUMAN),
    ("I want to talk to a real person", REQUEST_HUMAN),
    ("officer ni ivvandi", REQUEST_HUMAN),
    ("aal kitta pesanum", REQUEST_HUMAN),
    ("मैं मशीन से बात नहीं करूँगा", REFUSE_AI),
    ("I won't talk to a machine", REFUSE_AI),
    ("are you a robot?", ASK_ROBOT),
    ("kya aap machine ho?", ASK_ROBOT),
    ("boat kab aayegi?", STATUS_QUERY),
    ("any update on my parents?", STATUS_QUERY),
    ("eppudu vastaru?", STATUS_QUERY),
    ("are you deaf? my kid is on the roof", ANGER),
])
def test_intents_by_rule(text, intent):
    assert intent in detect(text)


def test_refusing_the_machine_is_not_also_a_request():
    assert detect("machine se baat nahi, insaan se baat karao") == {REFUSE_AI}


@pytest.mark.parametrize("text", ["we are stuck on the roof", "हम छत पर हैं, पानी कमर तक है",
                                  "మేము ఇక్కడ ఉన్నాము", "near the temple", "4 people, no one hurt"])
def test_ordinary_answers_trigger_nothing(text):
    assert detect(text) == set()


# ---------------------------------------------------------------- greeting

def test_greeting_says_automated_and_what_it_does_and_asks_danger():
    s = session({})
    g = s.ticket.transcript[0].text
    assert g.startswith("फ़्लड हेल्पलाइन") and "ऑटोमैटिक असिस्टेंट" in g and "ऑफिसर" in g and "खतरा" in g
    assert "लाइन में" not in g                             # "you are in line" before they've said a word
    r = s.handle("nahi", "hi-IN")                          # quick-parsed as the danger answer
    assert r["used_llm"] is False and s.ticket.danger.injured is False


# ---------------------------------------------------------------- asking for a person

def test_first_request_for_a_person_gets_in_line_and_one_question():
    s = session({"mujhe insaan se baat karni hai": {}})
    r = s.handle("mujhe insaan se baat karni hai", "hi-IN")
    assert phrases.say("request_human_ack", "hi-IN") in r["reply"]
    assert r["action"].startswith("ask:") and not r["waiting"]
    assert "सबसे ज़रूरी" not in r["reply"]                 # not "most urgent"
    assert s.ticket.escalate_to_human is False


def test_second_request_means_waiting_no_more_questions():
    s = session({"mujhe insaan se baat karni hai": {}, "hum Velachery mein hain": dict(locality="Velachery")})
    s.handle("mujhe insaan se baat karni hai", "hi-IN")
    r = s.handle("mujhe insaan se baat karni hai", "hi-IN")
    assert r["waiting"] and r["action"] == "wait" and not r["done"]
    assert phrases.say("still_in_line", "hi-IN") in r["reply"]
    r = s.handle("hum Velachery mein hain", "hi-IN")       # still listening, still filling the ticket
    assert s.ticket.location.locality == "Velachery"
    assert r["reply"] == phrases.say("noted", "hi-IN") and r["action"] == "wait"
    assert r["reassure"] == phrases.say("still_in_line", "hi-IN")


def test_an_operator_is_free_so_the_call_is_passed_on(monkeypatch):
    monkeypatch.setattr(dialogue, "HUMAN_OPERATORS_BUSY", 2)
    s = session({})
    r = s.handle("I want to talk to a real person", "en-IN")
    assert r["action"] == "handoff" and r["waiting"]


def test_refusing_the_machine_waits_at_once():
    s = session({})
    r = s.handle("मैं मशीन से बात नहीं करूँगा", "hi-IN")
    assert r["waiting"] and r["action"] == "wait"
    assert "caller declined the AI" in s.ticket.followup_reasons


def test_while_waiting_p0_evidence_still_alerts():
    s = session({"chest": dict(water_level="chest", water_rising=True)})
    s.handle("मैं मशीन से बात नहीं करूँगा", "hi-IN")
    r = s.handle("chest", "hi-IN")
    assert s.ticket.priority == "P0" and phrases.say("urgent", "hi-IN") in r["reply"]


def test_silence_while_waiting_says_nothing():
    s = session({"हम्म": {}})
    s.handle("मैं मशीन से बात नहीं करूँगा", "hi-IN")
    assert s.handle("हम्म", "hi-IN")["reply"] == ""


def test_hanging_up_while_waiting_is_a_callback():
    s = session({})
    s.handle("I won't talk to a machine", "en-IN")
    t = s.drop()
    assert "hung up while waiting for an officer: call back" in t.followup_reasons


# ---------------------------------------------------------------- robot, status, anger

def test_are_you_a_robot_is_answered_honestly_then_the_question():
    s = session({})
    r = s.handle("are you a robot?", "en-IN")
    assert phrases.say("yes_automated", "en-IN") in r["reply"] and r["action"].startswith("ask:")


def test_status_question_gets_only_the_fixed_reply():
    s = session({"boat kab aayegi?": {}})
    r = s.handle("boat kab aayegi?", "hi-IN")
    assert r["reply"].startswith(phrases.say("status_deflect", "hi-IN"))
    assert phrases.say("ans_when_help", "hi-IN") not in r["reply"]
    assert not sounds_like_promise(r["reply"])


def test_anger_is_distress_not_abuse():
    line = "are you deaf? my kid is on the roof"
    s = session({line: dict(vulnerable=["child"], floor="terrace", ack="Okay, terrace.")})
    r = s.handle(line, "en-IN")
    assert r["reply"].startswith(phrases.say("anger_ack", "en-IN"))
    assert "calm down" not in r["reply"].lower()
    assert "child" in s.ticket.vulnerable                  # still extracting
    calm = session({"my kid is on the roof": dict(vulnerable=["child"], floor="terrace")})
    calm.handle("my kid is on the roof", "en-IN")
    assert s.ticket.priority == calm.ticket.priority       # tone never changes priority


# ---------------------------------------------------------------- honest goodbye per priority

def _complete(table_extra, final_extraction):
    lines = {"l1": dict(locality="Velachery", injured=False, needs=["rescue"]),
             "l2": dict(street="Nehru Street", door_no="5", floor="first"),
             "l3": dict(people_count=2), "l4": {}, "l5": final_extraction, "yes": dict(confirmation="yes")}
    lines.update(table_extra)
    s = session(lines, greet=False)
    r = None
    for line in ["l1", "l2", "l3", "l4", "l5", "yes", "yes"]:
        r = s.handle(line, "en-IN")
        if r["done"] or r["waiting"]:
            break
    return s, r


def test_p2_is_reviewed_not_called_back():
    s, r = _complete({}, dict(water_level="ankle"))
    assert s.ticket.priority == "P2" and r["done"] and not r["waiting"]
    assert "an officer will review them" in r["reply"] and "call you back" not in r["reply"]


def test_p1_stays_on_the_line_with_the_battery_offer():
    s, r = _complete({"l4": dict(vulnerable=["elderly"])}, dict(water_level="ankle"))
    assert s.ticket.priority == "P1" and r["waiting"] and not r["done"]
    assert "An officer will speak to you" in r["reply"] and "you can hang up" in r["reply"]
    assert "call this number" not in r["reply"]            # no callback promise: callbacks aren't built


def test_p0_is_alerted_and_stays_on_the_line():
    s, r = _complete({}, dict(water_level="chest"))
    assert s.ticket.priority == "P0" and r["waiting"]
    assert "An officer is being alerted now" in r["reply"]


def test_no_p2_p3_goodbye_promises_a_call_in_any_language():
    for lang in LANGS:
        for key in ("close",):
            line = phrases.say(key, lang, digits="1 2 3 4")
            for words in ("call you back", "वापस कॉल", "మళ్ళీ కాల్ చేస్తాము", "திரும்ப கூப்பிடுவோம்"):
                assert words not in line, (lang, key)


def test_every_language_has_every_new_line():
    keys = ("p0_wait", "p1_wait", "still_in_line", "request_human_ack", "anger_ack", "yes_automated",
            "status_deflect", "new_info", "noted", "one_person")
    for lang in LANGS:
        for k in keys:
            assert phrases.has(k, lang), (k, lang)


def test_no_new_line_gives_a_time():
    for lang in LANGS:
        for k in ("p0_wait", "p1_wait", "still_in_line", "request_human_ack", "status_deflect", "one_person"):
            assert not sounds_like_promise(phrases.say(k, lang, digits="1 2")), (k, lang)


# ---------------------------------------------------------------- noise ladder

def test_unclear_turns_climb_the_ladder():
    s = session({"x": dict(unclear=True)})
    r1, r2, r3 = (s.handle("x", "en-IN") for _ in range(3))
    assert "one person" not in r1["reply"]                 # 1: simpler wording
    assert phrases.say("one_person", "en-IN") in r2["reply"] and r2["action"] != "handoff"  # 2: one person
    assert r3["action"] == "handoff"                       # 3: a human


# ---------------------------------------------------------------- the live call on 9 Nov, 12:21

def test_request_for_a_person_is_not_echoed_back():
    s = session({"मुझे इंसान से बात करनी है।": dict(ack="इंसान से बात करनी है, ठीक।", spoken_language="hi-IN")})
    r = s.handle("मुझे इंसान से बात करनी है।", "hi-IN")
    assert r["reply"].startswith(phrases.say("request_human_ack", "hi-IN"))
    assert "इंसान से बात करनी है, ठीक" not in r["reply"]


def test_dont_know_with_a_fact_goes_to_the_llm_and_switches_language():
    line = "తెలియదు, నీళ్ళు ఎక్కువ ఉన్నాయి."      # "don't know, there's a lot of water"
    s = session({"मुझे इंसान से बात करनी है।": dict(spoken_language="hi-IN"),
                 line: dict(dont_know=True, water_rising=None, spoken_language="te-IN", needs=["rescue"])})
    s.handle("मुझे इंसान से बात करनी है।", "hi-IN")
    r = s.handle(line, "te-IN")
    assert r["used_llm"] is True and r["reply_lang"] == "te-IN"


def test_plain_dont_know_still_skips_the_llm():
    from app.quick_parse import quick_parse
    for t in ("pata nahi", "తెలియదు సార్", "I don't know", "नहीं पता जी"):
        e = quick_parse(t, "ask:danger")
        assert e is not None and e.dont_know, t
    assert quick_parse("తెలియదు, నీళ్ళు ఎక్కువ ఉన్నాయి.", "ask:danger") is None