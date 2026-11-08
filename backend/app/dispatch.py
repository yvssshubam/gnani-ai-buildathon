"""What happens to a ticket after the call: the control room assigns a team, the team reports back.

Kept in its own SQLite table so the call engine's Ticket model doesn't change. The dashboard
merges both: the ticket says what the caller told us, dispatch says what we did about it.

Field statuses, in order: waiting -> assigned -> on_the_way -> rescued | not_found
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Optional

FIELD_STATUSES = ("assigned", "on_the_way", "rescued", "not_found")
CLOSED = ("rescued", "not_found")

# Synthetic teams for the demo. In deployment these come from the control room's roster.
# lat/lon = where the team is based (used for "nearest free team"); deep_water = can it go
# where water is waist-deep or more; medical = can treat on the spot.
TEAMS = [
    {"id": "boat-1", "name": "Boat team 1", "kind": "Boat, 6 seats", "seats": 6,
     "deep_water": True, "medical": False, "lat": 13.0060, "lon": 80.2550},
    {"id": "boat-2", "name": "Boat team 2", "kind": "Boat, 6 seats", "seats": 6,
     "deep_water": True, "medical": False, "lat": 12.9750, "lon": 80.2210},
    {"id": "boat-3", "name": "Boat team 3", "kind": "Boat, 8 seats", "seats": 8,
     "deep_water": True, "medical": False, "lat": 12.9380, "lon": 80.2050},
    {"id": "fire-1", "name": "Fire and rescue 1", "kind": "Truck, rope rescue", "seats": 10,
     "deep_water": False, "medical": False, "lat": 12.9250, "lon": 80.1150},
    {"id": "med-1", "name": "Medical team 1", "kind": "Ambulance boat", "seats": 4,
     "deep_water": True, "medical": True, "lat": 13.0220, "lon": 80.2260},
]
_TEAM_IDS = {t["id"] for t in TEAMS}

# The human desk shown on the dashboard: the AI answers because every operator is on a call.
HUMAN_OPERATORS = int(os.getenv("HUMAN_OPERATORS", "3"))
HUMAN_OPERATORS_BUSY = int(os.getenv("HUMAN_OPERATORS_BUSY", "3"))


class DispatchError(ValueError):
    pass


class Dispatch:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("""CREATE TABLE IF NOT EXISTS dispatch (
            ticket_id TEXT PRIMARY KEY, created_at REAL, team_id TEXT, field_status TEXT,
            taken_over INTEGER DEFAULT 0, events TEXT DEFAULT '[]')""")
        self._db.execute("CREATE TABLE IF NOT EXISTS dispatch_settings (key TEXT PRIMARY KEY, value TEXT)")
        self._db.commit()

    # ------------------------------------------------------------- shift
    def shift_start(self) -> float:
        """Tickets from before this moment are hidden from the board (test calls, last shift)."""
        with self._lock:
            row = self._db.execute("SELECT value FROM dispatch_settings WHERE key = 'shift_start'").fetchone()
        return float(row[0]) if row else 0.0

    def start_shift(self) -> float:
        now = time.time()
        with self._lock:
            self._db.execute("INSERT INTO dispatch_settings (key, value) VALUES ('shift_start', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (str(now),))
            self._db.commit()
        return now

    # ------------------------------------------------------------- reads
    def get(self, ticket_id: str) -> dict:
        with self._lock:  # reads too: one SQLite connection, used from several threads
            row = self._db.execute("SELECT ticket_id, created_at, team_id, field_status, taken_over, events "
                                   "FROM dispatch WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not row:
            return {"ticket_id": ticket_id, "created_at": None, "team_id": None, "team": None,
                    "field_status": None, "taken_over": False, "events": []}
        team = next((t for t in TEAMS if t["id"] == row[2]), None)
        return {"ticket_id": row[0], "created_at": row[1], "team_id": row[2], "team": team,
                "field_status": row[3], "taken_over": bool(row[4]), "events": json.loads(row[5] or "[]")}

    def all(self) -> dict[str, dict]:
        with self._lock:
            ids = [r[0] for r in self._db.execute("SELECT ticket_id FROM dispatch").fetchall()]
        return {i: self.get(i) for i in ids}

    def teams(self) -> list[dict]:
        """Teams with what they're doing now. A team is busy until its ticket is rescued or not found.
        Jobs from before the current shift don't count: starting a new shift frees every team."""
        busy, since = {}, self.shift_start()
        for d in self.all().values():
            last = d["events"][-1]["at"] if d["events"] else (d["created_at"] or 0)
            if d["team_id"] and d["field_status"] not in CLOSED and last >= since:
                busy[d["team_id"]] = d["ticket_id"]
        return [{**t, "busy_with": busy.get(t["id"])} for t in TEAMS]

    # ------------------------------------------------------------ writes
    def _save(self, d: dict, event: Optional[str]) -> dict:
        if event:
            d["events"].append({"at": time.time(), "text": event})
        with self._lock:
            self._db.execute(
                "INSERT INTO dispatch (ticket_id, created_at, team_id, field_status, taken_over, events) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(ticket_id) DO UPDATE SET created_at = excluded.created_at, "
                "team_id = excluded.team_id, field_status = excluded.field_status, "
                "taken_over = excluded.taken_over, events = excluded.events",
                (d["ticket_id"], d["created_at"], d["team_id"], d["field_status"], int(d["taken_over"]),
                 json.dumps(d["events"], ensure_ascii=False)))
            self._db.commit()
        return self.get(d["ticket_id"])

    def call_started(self, ticket_id: str) -> dict:
        d = self.get(ticket_id)
        if d["created_at"] is None:
            d["created_at"] = time.time()
            return self._save(d, "Call answered by Surgeline")
        return d

    def assign(self, ticket_id: str, team_id: str) -> dict:
        if team_id not in _TEAM_IDS:
            raise DispatchError(f"Unknown team: {team_id}")
        d = self.get(ticket_id)
        if d["field_status"] in CLOSED:
            raise DispatchError("This ticket is already closed")
        if d["team_id"] == team_id:
            return d  # already this team: keep its progress (e.g. "on the way")
        busy = next((t["busy_with"] for t in self.teams() if t["id"] == team_id), None)
        if busy and busy != ticket_id:
            raise DispatchError(f"That team is already on ticket {busy}")
        name = next(t["name"] for t in TEAMS if t["id"] == team_id)
        verb = "Reassigned to" if d["team_id"] and d["team_id"] != team_id else "Assigned to"
        d["team_id"], d["field_status"] = team_id, "assigned"
        return self._save(d, f"{verb} {name}")

    def field_update(self, ticket_id: str, status: str) -> dict:
        if status not in ("on_the_way", "rescued", "not_found"):
            raise DispatchError(f"Unknown status: {status}")
        d = self.get(ticket_id)
        if not d["team_id"]:
            raise DispatchError("Assign a team first")
        d["field_status"] = status
        event = {
            "on_the_way": "Team on the way. Callback queued: tell the caller a team is coming",
            "rescued": "Rescued. Ticket closed",
            "not_found": "Team could not find them. Verification callback queued",
        }[status]
        return self._save(d, event)

    def take_over(self, ticket_id: str, event: str = "Operator took over the call") -> dict:
        d = self.get(ticket_id)
        if d["taken_over"]:
            return d
        d["taken_over"] = True
        d["created_at"] = d["created_at"] or time.time()
        return self._save(d, event)


def sms_text(ticket: dict) -> str:
    """What the boat team's phone would receive. Plain text, short lines, works on any phone."""
    loc = ticket.get("location") or {}
    danger = ticket.get("danger") or {}
    lines = [f"SURGELINE {ticket['id']} {ticket.get('priority') or ''}".strip()]
    address = ", ".join(str(p) for p in (
        f"Door {loc['door_no']}" if loc.get("door_no") else None,
        loc.get("building"), loc.get("street"), loc.get("locality")) if p)
    lines.append(address or "Address not known yet")
    floor = loc.get("floor")
    if floor:
        lines.append(f"Floor: {floor}")
    if loc.get("landmark"):
        lines.append(f"Near: {loc['landmark']}")
    people = ticket.get("people_count")
    vulnerable = ticket.get("vulnerable") or []
    who = (f"{people} people" if people != 1 else "1 person") if people else "People: not known"
    if vulnerable:
        named = [v for v in vulnerable if v != "unspecified"]
        who += " incl. " + (", ".join(named) if named else "someone vulnerable")
    lines.append(who)
    if danger.get("water_level"):
        lines.append(f"Water: {danger['water_level']}" + (", rising" if danger.get("water_rising") else ""))
    if loc.get("lat") is not None and loc.get("lon") is not None:
        lines.append(f"Map: https://maps.google.com/?q={loc['lat']},{loc['lon']}")
    lines.append("Reply 1 on the way, 2 rescued, 3 not found")
    return "\n".join(lines)