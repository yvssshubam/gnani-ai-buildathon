"""AI notes, the operator-notes check, the simulated caller, and operator calls (no network)."""
import json

import pytest
from fastapi.testclient import TestClient

from app import main
from app.dispatch import Dispatch
from app.models import Extraction, Location, Ticket, Turn
from app.notes import Notes, clean_check_items, rule_check
from app.voice.stt import Transcript


def make_ticket(**kw):
    t = Ticket(id="7001", caller_number="SIM-1", **kw)
    t.transcript = [
        Turn(role="agent", text="Flood rescue line. What is happening?", lang="en-IN", ts=100.0),
        Turn(role="caller", text="हम वेलाचेरी में हैं, मकान नंबर बारह", lang="hi-IN", ts=106.0),
        Turn(role="agent", text="कितने लोग हैं?", lang="hi-IN", ts=110.0),
        Turn(role="caller", text="चार लोग, दादी चल नहीं पातीं", lang="hi-IN", ts=118.0),
    ]
    return t


class JsonLLM:
    """Answers chat_json with a fixed reply and records the prompts."""
    def __init__(self, reply=None, text=None, fail=False):
        self.reply, self.text, self.fail, self.prompts = reply, text, fail, []

    def chat_json(self, system, user, **kw):
        self.prompts.append(user)
        if self.fail:
            raise RuntimeError("rate limited")
        return self.reply, 10

    def chat_text(self, system, user, **kw):
        self.prompts.append(system + user)
        return self.text


class FakeOnly:
    def chat_json(self, system, user, **kw):
        raise NotImplementedError

    def chat_text(self, system, user, **kw):
        raise NotImplementedError


def notes_for(t, llm, tmp_path):
    return Notes(str(tmp_path / "n.db"), llm, lambda i: t if i == t.id else None)


# ---------- notes ----------

def test_notes_from_the_llm_are_saved_and_cleaned(tmp_path):
    t = make_ticket(location=Location(locality="Velachery", door_no="12"), people_count=4)
    llm = JsonLLM({"summary": "Family of 4 in Velachery, door 12.",
                   "details": [{"text": "Grandmother can't walk", "kind": "mobility", "at": "00:18"},
                               {"text": "", "kind": "other"}, {"text": "Odd kind", "kind": "weird", "at": "00:20"}],
                   "translations": [{"i": 1, "en": "We are in Velachery, house number twelve"},
                                    {"i": 0, "en": "should be ignored: agent line"},
                                    {"i": 99, "en": "no such line"}]})
    n = notes_for(t, llm, tmp_path).update_now("7001")
    assert n["summary"] == "Family of 4 in Velachery, door 12."
    assert n["details"] == [{"text": "Grandmother can't walk", "kind": "mobility", "at": "00:18"},
                            {"text": "Odd kind", "kind": "other", "at": "00:20"}]
    assert n["translations"] == {"1": "We are in Velachery, house number twelve"}
    # the prompt asks to translate only caller lines not yet translated, and shows times from the call start
    assert "Translate: 1, 3" in llm.prompts[0] and "[3] 00:18 Caller:" in llm.prompts[0]


def test_already_translated_lines_are_not_sent_again(tmp_path):
    t = make_ticket()
    llm = JsonLLM({"summary": "s", "details": [], "translations": [{"i": 1, "en": "one"}, {"i": 3, "en": "three"}]})
    n = notes_for(t, llm, tmp_path)
    n.update_now("7001")
    n.update_now("7001")
    assert "Translate: none" in llm.prompts[1]


def test_llm_failure_keeps_previous_notes(tmp_path):
    t = make_ticket()
    llm = JsonLLM({"summary": "Good summary", "details": [{"text": "Wire in the water", "kind": "hazard", "at": "00:10"}], "translations": []})
    n = notes_for(t, llm, tmp_path)
    n.update_now("7001")
    llm.fail = True
    after = n.update_now("7001")
    assert after["summary"] == "Good summary" and after["details"][0]["text"] == "Wire in the water"


def test_offline_notes_come_from_the_ticket_fields(tmp_path):
    t = make_ticket(location=Location(locality="Velachery", street="Gandhi Street"), people_count=4, vulnerable=["elderly"])
    t.danger.water_level, t.danger.water_rising = "waist", True
    n = notes_for(t, FakeOnly(), tmp_path).update_now("7001")
    assert n["summary"] == "4 people, including elderly at Gandhi Street, Velachery. Water at waist, rising."


# ---------- check ----------

def test_check_drops_quotes_the_caller_never_said_and_sorts_by_importance(tmp_path):
    t = make_ticket()
    llm = JsonLLM({"items": [
        {"status": "match", "topic": "People", "operator": "4 ppl", "call": "4 people", "quote": "चार लोग", "at": "00:18"},
        {"status": "differs", "topic": "Door number", "operator": "21", "call": "12", "quote": "मकान नंबर बारह", "at": "00:06"},
        {"status": "missing", "topic": "Mobility", "operator": None, "call": "Grandmother can't walk", "quote": "made up words", "at": "00:18"},
        {"status": "bogus", "topic": "x"}]})
    out = notes_for(t, llm, tmp_path).check("7001", "velachery door 21, 4 ppl")
    items = out["check"]
    assert [i["status"] for i in items] == ["differs", "missing", "match"]
    assert items[0]["quote"] == "मकान नंबर बारह"
    assert items[1]["quote"] is None  # not in the transcript, so not shown
    assert out["operator_notes"] == "velachery door 21, 4 ppl" and out["checked_at"]


def test_offline_rule_check(tmp_path):
    t = make_ticket(location=Location(locality="Velachery", door_no="12"), people_count=4)
    t.danger.water_level = "waist"
    items = rule_check(t.model_dump(), "Velachery door 21, 4 ppl")
    got = {i["topic"]: i["status"] for i in items}
    assert got == {"Door number": "differs", "Water level": "missing", "Area": "match", "People": "match"}
    door = next(i for i in items if i["topic"] == "Door number")
    assert (door["operator"], door["call"]) == ("21", "12")


def test_clean_check_items_rejects_junk():
    assert clean_check_items([{"status": "match"}, "junk", {"status": "nope"}], set()) == [
        {"status": "match", "topic": "Detail", "operator": None, "call": None, "quote": None, "at": None}]


# ---------- simulated caller ----------

def test_simulated_caller_reply(tmp_path):
    t = make_ticket()
    llm = JsonLLM(text="Caller: हम दूसरी मंज़िल पर हैं")
    reply = notes_for(t, llm, tmp_path).caller_reply("7001", "Family of 4 in Velachery", "hi-IN")
    assert reply == "हम दूसरी मंज़िल पर हैं"
    assert "Family of 4 in Velachery" in llm.prompts[0] and "Hindi" in llm.prompts[0]
    assert notes_for(t, FakeOnly(), tmp_path).caller_reply("7001", "x", "hi-IN") is None


# ---------- operator calls over HTTP ----------

class FakeSTT:
    def __init__(self):
        self.queue = []

    async def transcribe(self, audio, *, filename="turn.wav", previous_text=None, **kw):
        text, lang = self.queue.pop(0)
        return Transcript(text=text, language=lang, seconds=0.2)


class StepLLM:
    def __init__(self):
        self.calls = []

    def extract(self, text, last_q, known):
        self.calls.append((text, last_q))
        return Extraction(locality="Velachery", door_no="12", people_count=4)


@pytest.fixture
def api(tmp_path, monkeypatch):
    stt = FakeSTT()
    llm = StepLLM()
    monkeypatch.setitem(main.voice, "stt", stt)
    monkeypatch.setitem(main.voice, "tts", object())
    monkeypatch.setattr(main, "llm", llm)
    monkeypatch.setattr(main, "dispatch", Dispatch(str(tmp_path / "d.db")))
    monkeypatch.setattr(main, "notes", Notes(str(tmp_path / "n.db"), FakeOnly(), main.store.get))
    # One event loop for the whole test, as on the real server. Without `with`, each request
    # gets its own loop, and a note-taker started in one request can be dropped half-way.
    with TestClient(main.app) as c:
        c.stt, c.llm = stt, llm
        yield c


def test_operator_call_records_both_sides_and_fills_the_ticket(api):
    call_id = api.post("/api/operator/calls", json={}).json()["call_id"]
    api.stt.queue += [("Where are you?", "en-IN"), ("हम वेलाचेरी में हैं, मकान नंबर बारह, चार लोग", "hi-IN")]
    r1 = api.post(f"/api/operator/calls/{call_id}/turn?speaker=operator", content=b"op").json()
    assert r1["heard"] == "Where are you?" and r1["ticket"]["location"]["locality"] is None
    r2 = api.post(f"/api/operator/calls/{call_id}/turn?speaker=caller", content=b"caller").json()
    t = r2["ticket"]
    assert (t["location"]["locality"], t["location"]["door_no"], t["people_count"], t["language"]) == ("Velachery", "12", 4, "hi-IN")
    assert [x["role"] for x in t["transcript"]] == ["operator", "caller"]
    assert api.llm.calls == [("हम वेलाचेरी में हैं, मकान नंबर बारह, चार लोग", "operator: Where are you?")]

    import time
    for _ in range(50):  # notes are written in the background, after the turn's reply
        row = next(x for x in api.get("/api/board").json()["tickets"] if x["id"] == call_id)
        if row["notes"]["summary"]:
            break
        time.sleep(0.02)
    assert row["operator_live"] and row["live"] and not row["needs_operator"]
    assert row["notes"]["summary"]

    out = api.post(f"/api/tickets/{call_id}/notes/check", json={"operator_notes": "Velachery door 21, 4 ppl"}).json()
    assert {i["topic"]: i["status"] for i in out["check"]}["Door number"] == "differs"

    ended = api.post(f"/api/operator/calls/{call_id}/end").json()
    assert ended["call_state"] == "completed" and not ended["operator_live"]
    assert api.post(f"/api/operator/calls/{call_id}/turn?speaker=caller", content=b"x").status_code == 409


def test_take_over_stops_the_ai(api):
    call_id = api.post("/api/calls", json={}).json()["call_id"]
    assert not main.sessions[call_id].done
    row = api.post(f"/api/tickets/{call_id}/take-over").json()
    assert main.sessions[call_id].done and row["operator_live"] and row["dispatch"]["taken_over"]


def test_bad_operator_requests(api):
    call_id = api.post("/api/operator/calls", json={}).json()["call_id"]
    assert api.post(f"/api/operator/calls/{call_id}/turn?speaker=robot", content=b"x").status_code == 400
    assert api.post(f"/api/operator/calls/{call_id}/turn", content=b"").status_code == 400
    assert api.post("/api/operator/calls/nope/turn", content=b"x").status_code == 404
    assert api.post("/api/sim/nope/caller-reply", json={"facts": "x"}).status_code == 404
    assert api.post(f"/api/sim/{call_id}/caller-reply", json={"facts": "x"}).json() == {"text": None}
    assert json.loads(api.put(f"/api/tickets/{call_id}/notes", json={"operator_notes": "abc"}).text)["operator_notes"] == "abc"