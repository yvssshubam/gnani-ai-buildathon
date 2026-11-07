"""SQLite storage. Each ticket is stored as one JSON document."""
from __future__ import annotations

import json
import random
import sqlite3
import threading
import time
from typing import Optional

from .models import Ticket


class TicketStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS tickets ("
                " id TEXT PRIMARY KEY,"
                " data TEXT NOT NULL,"
                " updated_at REAL NOT NULL)"
            )
            self._conn.commit()

    def _new_id(self) -> str:
        """4-digit IDs: easy to read out on a phone call ("four seven two one")."""
        for _ in range(1000):
            candidate = f"{random.randint(1000, 9999)}"
            if self.get(candidate) is None:
                return candidate
        raise RuntimeError("Ran out of ticket IDs")

    def create(self, caller_number: str) -> Ticket:
        ticket = Ticket(id=self._new_id(), caller_number=caller_number)
        self.save(ticket)
        return ticket

    def save(self, ticket: Ticket) -> None:
        ticket.updated_at = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tickets (id, data, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (ticket.id, ticket.model_dump_json(), ticket.updated_at),
            )
            self._conn.commit()

    def get(self, ticket_id: str) -> Optional[Ticket]:
        with self._lock:
            row = self._conn.execute("SELECT data FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return Ticket.model_validate(json.loads(row[0])) if row else None

    def list(self) -> list[Ticket]:
        with self._lock:
            rows = self._conn.execute("SELECT data FROM tickets ORDER BY updated_at DESC").fetchall()
        return [Ticket.model_validate(json.loads(r[0])) for r in rows]