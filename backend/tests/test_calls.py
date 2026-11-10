"""End-to-end call scenarios through the HTTP API, using the offline fake brain."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def call(*utterances, lang=None):
    start = client.post("/api/calls", json={}).json()
    cid = start["call_id"]
    replies = []
    r = None
    for u in utterances:
        r = client.post(f"/api/calls/{cid}/turn", json={"text": u, "lang": lang}).json()
        replies.append((r["action"], r["reply"]))
    return cid, replies, r


def test_full_call_happy_path():
    cid, replies, r = call(
        "Water is coming into our house in Velachery, my grandmother is with us",
        "nobody is hurt but the water is rising",
        "Bharathi street, door no 12, first floor",
        "we are 4 people",
        "water is at knee level",
        "yes correct",
    )
    actions = [a for a, _ in replies]
    assert actions == ["ask:danger", "ask:street", "ask:people", "ask:water", "readback", "close"], actions
    t = r["ticket"]
    # P0: the AI's questions are done, but the caller stays on the line for an officer (waiting room)
    assert r["done"] is False and r["waiting"] is True
    assert "An officer is being alerted now" in replies[-1][1]
    assert t["location"]["locality"] == "Velachery"
    assert t["location"]["confidence"] == "exact"
    assert t["location"]["confirmed"] is True
    assert t["people_count"] == 4
    assert "elderly" in t["vulnerable"]
    assert t["priority"] == "P0"  # rising water + elderly + knee level
    assert t["escalate_to_human"] is True
    assert t["status"] == "new" and t["call_state"] == "in_progress"
    assert " ".join(cid) in replies[-1][1]  # ticket digits spoken in the closing line


def test_p0_triggers_urgent_preface_once():
    _, replies, r = call(
        "Help, water is at chest level and rising, I have a baby",
        "Tambaram, Gandhi road, ground floor",
    )
    assert r["ticket"]["priority"] == "P0"
    assert "most urgent" in replies[0][1]
    assert "most urgent" not in replies[1][1]


def test_vague_location_ends_with_callback_flag():
    _, replies, r = call(
        "we are stuck, water everywhere",
        "nobody is hurt",
        "I don't know, near some temple",
        "I don't know",
        "3 people",
        "no",
        "knee",
        "yes",
    )
    t = r["ticket"]
    assert r["waiting"] is True                       # P1: stays in line for an officer
    assert t["location"]["confidence"] == "unknown"
    assert t["status"] == "needs_callback"
    assert "An officer will speak to you" in replies[-1][1]


def test_correction_at_readback():
    cid, replies, r = call(
        "Water in our house in Adyar, nobody is hurt",
        "Lake street, door no 5, second floor",
        "2 people",
        "no",
        "ankle",
        "no, it is third floor",
        "yes",
    )
    actions = [a for a, _ in replies]
    assert actions[-3:] == ["readback", "readback", "close"], actions
    t = r["ticket"]
    assert t["location"]["floor"] == "third"
    assert t["location"]["confirmed"] is True


def test_dropped_call_keeps_partial_ticket():
    cid, _, _ = call("We are trapped in Mudichur, water rising")
    t = client.post(f"/api/calls/{cid}/drop").json()["ticket"]
    assert t["call_state"] == "dropped"
    assert t["status"] == "needs_callback"
    assert t["location"]["locality"] == "Mudichur"
    assert t["danger"]["water_rising"] is True


def test_asking_for_a_person_is_kept_in_line_not_marked_urgent():
    """Design v2, 5.4: no operator free -> "an officer will speak to you when one is free", and the
    questions go on (so the caller doesn't have to repeat everything to the officer).
    It is not a P0: the caller must not hear "your case is marked most urgent"."""
    _, replies, r = call("I want to talk to a real person, we are in Saidapet")
    assert r["ticket"]["escalate_to_human"] is False
    assert "most urgent" not in replies[0][1]
    assert "an officer will speak to you when one is free" in replies[0][1]
    assert "one question" not in replies[0][1]            # it was never just one
    assert replies[0][0].startswith("ask:")
    assert "caller asked for a person" in r["ticket"]["followup_reasons"]


def test_turn_limit_closes_call():
    texts = ["hmm"] * 12
    _, replies, r = call(*texts)
    assert r["done"] or r["waiting"]                  # never loops: handed to an officer
    assert any(a == "handoff" for a, _ in replies)


def test_ticket_list_sorted_by_priority():
    call("food needed, no water inside, we are fine in Porur")
    call("water at neck level in Ennore")
    tickets = client.get("/api/tickets").json()
    priorities = [t["priority"] for t in tickets]
    assert priorities == sorted(priorities)


def test_status_update():
    cid, _, _ = call("we are stuck in Kolathur")
    t = client.patch(f"/api/tickets/{cid}", json={"status": "assigned"}).json()
    assert t["status"] == "assigned"