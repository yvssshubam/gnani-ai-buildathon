"""Control room: assigning teams, field updates, take-over, the board and the team's SMS."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.dispatch import Dispatch, DispatchError, sms_text


@pytest.fixture
def d(tmp_path):
    return Dispatch(str(tmp_path / "d.db"))


def test_full_rescue_flow(d):
    d.call_started("1")
    d.assign("1", "boat-1")
    d.field_update("1", "on_the_way")
    out = d.field_update("1", "rescued")
    assert out["field_status"] == "rescued" and out["team"]["name"] == "Boat team 1"
    assert [e["text"].split(".")[0] for e in out["events"]] == [
        "Call answered by Surgeline", "Assigned to Boat team 1", "Team on the way", "Rescued"]


def test_a_team_is_busy_until_its_ticket_closes(d):
    d.assign("1", "boat-1")
    with pytest.raises(DispatchError, match="already on ticket 1"):
        d.assign("2", "boat-1")
    d.field_update("1", "not_found")
    assert d.assign("2", "boat-1")["team_id"] == "boat-1"


def test_reassigning_the_same_team_keeps_its_progress(d):
    d.assign("1", "boat-1")
    d.field_update("1", "on_the_way")
    assert d.assign("1", "boat-1")["field_status"] == "on_the_way"


def test_reassign_to_another_team_frees_the_first(d):
    d.assign("1", "boat-1")
    out = d.assign("1", "boat-2")
    assert out["events"][-1]["text"] == "Reassigned to Boat team 2"
    assert next(t for t in d.teams() if t["id"] == "boat-1")["busy_with"] is None


def test_rules(d):
    with pytest.raises(DispatchError):
        d.assign("1", "submarine")
    with pytest.raises(DispatchError, match="Assign a team first"):
        d.field_update("1", "on_the_way")
    d.assign("1", "boat-1")
    d.field_update("1", "rescued")
    with pytest.raises(DispatchError, match="closed"):
        d.assign("1", "boat-2")


def test_take_over_is_logged_once(d):
    d.take_over("1")
    out = d.take_over("1")
    assert out["taken_over"] and len(out["events"]) == 1


def test_survives_a_restart(tmp_path):
    path = str(tmp_path / "d.db")
    Dispatch(path).assign("1", "boat-3")
    assert Dispatch(path).get("1")["team_id"] == "boat-3"


def test_sms_text():
    t = {"id": "7001", "priority": "P0", "people_count": 1, "vulnerable": ["elderly", "unspecified"],
         "location": {"door_no": "12", "street": "Gandhi Street", "locality": "Velachery", "floor": "1",
                      "lat": 12.98, "lon": 80.21},
         "danger": {"water_level": "chest", "water_rising": True}}
    sms = sms_text(t)
    assert sms.splitlines()[0] == "SURGELINE 7001 P0"
    assert "Door 12, Gandhi Street, Velachery" in sms and "1 person incl. elderly" in sms
    assert "Water: chest, rising" in sms and "maps.google.com/?q=12.98,80.21" in sms
    assert sms_text({"id": "9", "location": {}, "danger": {}}).splitlines()[1] == "Address not known yet"


# ---------- HTTP ----------

@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "dispatch", Dispatch(str(tmp_path / "board.db")))
    return TestClient(main.app)


def test_board_and_actions(api):
    tid = api.post("/api/calls", json={}).json()["call_id"]
    board = api.get("/api/board").json()
    row = next(t for t in board["tickets"] if t["id"] == tid)
    assert row["live"] and row["dispatch"]["created_at"] and board["desk"]["operators"] >= 1
    assert len(board["teams"]) >= 3

    assert api.post(f"/api/tickets/{tid}/field", json={"status": "rescued"}).status_code == 409
    r = api.post(f"/api/tickets/{tid}/assign", json={"team_id": "boat-1"})
    assert r.status_code == 200 and r.json()["dispatch"]["field_status"] == "assigned"
    assert api.post(f"/api/tickets/{tid}/field", json={"status": "on_the_way"}).json()["dispatch"]["field_status"] == "on_the_way"
    assert api.post(f"/api/tickets/{tid}/take-over").json()["dispatch"]["taken_over"]
    assert api.get(f"/api/rescuer/{tid}").json()["sms"].startswith(f"SURGELINE {tid}")
    assert api.post("/api/tickets/nope/assign", json={"team_id": "boat-1"}).status_code == 404


def test_new_shift_hides_old_tickets_and_frees_teams(api):
    old = api.post("/api/calls", json={}).json()["call_id"]
    api.post(f"/api/tickets/{old}/assign", json={"team_id": "boat-1"})
    assert next(t for t in api.get("/api/board").json()["teams"] if t["id"] == "boat-1")["busy_with"] == old

    import time as _t
    _t.sleep(0.01)
    assert api.post("/api/shift/start").status_code == 200
    board = api.get("/api/board").json()
    assert old not in [t["id"] for t in board["tickets"]]
    assert next(t for t in board["teams"] if t["id"] == "boat-1")["busy_with"] is None

    new = api.post("/api/calls", json={}).json()["call_id"]
    assert new in [t["id"] for t in api.get("/api/board").json()["tickets"]]
    assert api.get(f"/api/tickets/{old}").status_code == 200  # still there, just hidden


def test_teams_have_locations(api):
    for t in api.get("/api/board").json()["teams"]:
        assert -90 <= t["lat"] <= 90 and -180 <= t["lon"] <= 180 and t["seats"] > 0
