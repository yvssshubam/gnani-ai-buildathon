"""HTTP API for Phase 1 (text mode).

Run:  uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import random
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .dialogue import CallSession
from .llm import make_llm
from .models import Status
from .store import TicketStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="Flood SOS backend", version="0.1-phase1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

store = TicketStore(settings.db_path)
llm = make_llm()
sessions: dict[str, CallSession] = {}  # call_id (= ticket id) -> live session


def fake_caller_number() -> str:
    """Obviously synthetic numbers: the challenge allows no real phone numbers."""
    return f"SIM-{random.randint(10000, 99999)}"


class StartCall(BaseModel):
    caller_number: Optional[str] = None


class CallerTurn(BaseModel):
    text: str
    lang: Optional[str] = None  # e.g. "ta-IN" from Prisma; if empty we guess from the script


class StatusUpdate(BaseModel):
    status: Status


@app.get("/api/health")
def health():
    return {"ok": True, "llm": settings.llm_provider, "model": settings.llm_model if settings.llm_provider != "fake" else None}


@app.post("/api/calls")
def start_call(body: StartCall):
    ticket = store.create(body.caller_number or fake_caller_number())
    session = CallSession(ticket, llm, store)
    sessions[ticket.id] = session
    return {"call_id": ticket.id, "ticket_id": ticket.id, "caller_number": ticket.caller_number,
            "greeting": session.greeting()}


@app.post("/api/calls/{call_id}/turn")
def caller_turn(call_id: str, body: CallerTurn):
    session = sessions.get(call_id)
    if not session:
        raise HTTPException(404, "No live call with that id")
    if not body.text.strip():
        raise HTTPException(400, "Empty utterance")
    return session.handle(body.text, body.lang)


@app.post("/api/calls/{call_id}/drop")
def drop_call(call_id: str):
    session = sessions.get(call_id)
    if not session:
        raise HTTPException(404, "No live call with that id")
    return {"ticket": session.drop().model_dump()}


@app.get("/api/tickets")
def list_tickets():
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    tickets = store.list()
    tickets.sort(key=lambda t: (order.get(t.priority, 9), -t.updated_at))
    return [t.model_dump() for t in tickets]


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    t = store.get(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    return t.model_dump()


@app.patch("/api/tickets/{ticket_id}")
def update_status(ticket_id: str, body: StatusUpdate):
    t = store.get(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    t.status = body.status
    store.save(t)
    if ticket_id in sessions:
        sessions[ticket_id].ticket.status = body.status
    return t.model_dump()