"""HTTP API. Phase 1: text calls (/api/calls). Phase 2: voice calls (/api/voice/...).

Run:  uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Optional

import re

import httpx
from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import prompts
from .config import settings
from .dialogue import CallSession, apply_extraction, known_summary
from .language import judge_turn
from .dispatch import HUMAN_OPERATORS, HUMAN_OPERATORS_BUSY, Dispatch, DispatchError, sms_text
from .llm import make_llm
from .models import CallState, Status, Turn
from .notes import Notes
from .priority import assess
from .store import TicketStore
from .voice.call import AUDIO_ROUTE, VoiceState, keyterms, speak, voice_turn
from .voice.gnani_http import GnaniError
from .voice.stt import PrismaSTT
from .voice.tts import TimbreTTS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="Flood SOS backend", version="0.1-phase1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

store = TicketStore(settings.db_path)
dispatch = Dispatch(settings.db_path)
llm = make_llm()
notes = Notes(settings.db_path, llm, lambda ticket_id: store.get(ticket_id))
operator_calls: set[str] = set()  # tickets where a human operator is on the line now
sessions: dict[str, CallSession] = {}  # call_id (= ticket id) -> live session
voice_states: dict[str, VoiceState] = {}  # call_id -> voice-only state (last reply, language)
voice: dict = {"stt": None, "tts": None, "caller_tts": None}   # Gnani clients, created on first use

MAX_AUDIO_BYTES = 5 * 1024 * 1024          # a 30 s WAV at 44.1 kHz is about 2.6 MB
AUDIO_NAME = re.compile(r"^[0-9a-f]{32}\.wav$")


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
    dispatch.call_started(ticket.id)
    return {"call_id": ticket.id, "ticket_id": ticket.id, "caller_number": ticket.caller_number,
            "greeting": session.greeting()}


@app.post("/api/calls/{call_id}/turn")
async def caller_turn(call_id: str, body: CallerTurn):
    session = sessions.get(call_id)
    if not session:
        raise HTTPException(404, "No live call with that id")
    if not body.text.strip():
        raise HTTPException(400, "Empty utterance")
    result = await run_in_threadpool(session.handle, body.text, body.lang)
    notes.schedule(call_id)  # background: the reply doesn't wait for the notes
    return result


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

# ------------------------------------------------------------------ Phase 2: voice

def _voice_clients() -> tuple[PrismaSTT, TimbreTTS]:
    if voice["stt"] is None:
        if not settings.gnani_api_key:
            raise HTTPException(503, "GNANI_API_KEY is not set in .env")
        client = httpx.AsyncClient(timeout=settings.gnani_timeout)
        voice["stt"] = PrismaSTT(client, keyterms=keyterms())
        voice["tts"] = TimbreTTS(client)
        voice["caller_tts"] = TimbreTTS(client, voices=settings.sim_caller_voices)
    return voice["stt"], voice["tts"]


@app.post("/api/voice/calls")
async def start_voice_call(body: StartCall):
    """Start a call and speak the greeting. Returns the same fields as /api/calls plus `audio`."""
    _, tts = _voice_clients()
    started = start_call(body)
    lang = prompts.GREETING["lang"]
    # No speech-to-text context from the greeting: it is bilingual and would push the first
    # transcription toward its language. From the first reply on, context is in the call's language.
    voice_states[started["call_id"]] = VoiceState(reply_lang=lang, last_agent_text=None)
    urls, tts_ms, error = await speak(tts, [started["greeting"]], lang)
    started.update({"greeting_lang": lang, "audio": urls, "tts_ms": tts_ms})
    if error:
        started["tts_error"] = error
    return started


@app.post("/api/voice/calls/{call_id}/turn")
async def voice_caller_turn(call_id: str, request: Request, filename: str = "turn.wav"):
    """Body: the raw audio of one caller turn (WAV, MP3, OGG, FLAC, AAC or M4A, at most 30 s).
    Returns the /turn result plus heard, heard_lang, stt_ms, tts_ms and audio (one URL per reply part)."""
    session = sessions.get(call_id)
    if not session or call_id not in voice_states:
        raise HTTPException(404, "No live voice call with that id")
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "Empty audio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio too large: send one caller turn, at most 30 seconds")
    stt, tts = _voice_clients()
    try:
        result = await voice_turn(session, voice_states[call_id], audio, filename, stt, tts)
        if result.get("heard"):
            notes.schedule(call_id)  # background: the reply doesn't wait for the notes
        return result
    except GnaniError as e:
        logging.getLogger("voice").warning("STT failed on call %s: %s", call_id, e)
        raise HTTPException(502, f"Speech recognition failed: {e}")


class Say(BaseModel):
    text: str
    lang: str = "hi-IN"


@app.post("/api/voice/say")
async def simulated_caller_line(body: Say):
    """Speak one scripted caller line with a caller voice (not the agent's), for simulated calls.
    The browser plays it, then sends the same audio to /turn, so it goes through real speech-to-text."""
    if not body.text.strip():
        raise HTTPException(400, "Empty text")
    _voice_clients()
    tts = voice["caller_tts"]
    try:
        await tts.synthesize(body.text, body.lang)
    except GnaniError as e:
        raise HTTPException(502, f"Couldn't make the caller's voice: {e}")
    return {"audio": AUDIO_ROUTE + tts.cached_path(body.text, body.lang).name}


@app.get("/api/voice/audio/{name}")
def voice_audio(name: str):
    """A spoken line from the TTS cache."""
    if not AUDIO_NAME.match(name):
        raise HTTPException(404, "Not found")
    path = Path(settings.tts_cache_dir) / name
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="audio/wav")


# ------------------------------------------------------------------ control room

ENDED_CALL_STATES = {"completed", "handed_off", "dropped"}


def _state(value) -> str:
    return getattr(value, "value", value) or ""


def _board_row(t, d: dict) -> dict:
    row = t.model_dump()
    call_state = _state(t.call_state)
    row["dispatch"] = d
    row["operator_live"] = t.id in operator_calls
    row["live"] = row["operator_live"] or (t.id in sessions and not sessions[t.id].done and call_state not in ENDED_CALL_STATES)
    # The AI handed over (or the caller asked for a person) and no operator has picked it up yet
    row["needs_operator"] = (call_state == "handed_off" or bool(t.escalate_to_human)) and not d["taken_over"]
    row["notes"] = notes.get(t.id)
    row["created_at"] = d["created_at"] or t.updated_at
    return row


@app.get("/api/board")
def board():
    """Everything the control room dashboard needs, in one poll. Only this shift's tickets."""
    dispatches = dispatch.all()
    since = dispatch.shift_start()
    rows = [_board_row(t, dispatches.get(t.id) or dispatch.get(t.id)) for t in store.list()]
    rows = [r for r in rows if (r["created_at"] or 0) >= since]
    return {"now": time.time(), "shift_start": since, "tickets": rows, "teams": dispatch.teams(),
            "desk": {"operators": HUMAN_OPERATORS, "busy": HUMAN_OPERATORS_BUSY}}


@app.post("/api/shift/start")
def start_shift():
    """Hide every ticket from before now (test calls, the last shift). Nothing is deleted."""
    return {"shift_start": dispatch.start_shift()}


class Assign(BaseModel):
    team_id: str


class FieldUpdate(BaseModel):
    status: str


def _ticket_or_404(ticket_id: str):
    t = store.get(ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    return t


@app.post("/api/tickets/{ticket_id}/assign")
def assign_team(ticket_id: str, body: Assign):
    t = _ticket_or_404(ticket_id)
    try:
        return _board_row(t, dispatch.assign(ticket_id, body.team_id))
    except DispatchError as e:
        raise HTTPException(409, str(e))


@app.post("/api/tickets/{ticket_id}/field")
def field_update(ticket_id: str, body: FieldUpdate):
    """The rescue team's buttons: on_the_way, rescued, not_found."""
    t = _ticket_or_404(ticket_id)
    try:
        return _board_row(t, dispatch.field_update(ticket_id, body.status))
    except DispatchError as e:
        raise HTTPException(409, str(e))


@app.post("/api/tickets/{ticket_id}/take-over")
def take_over(ticket_id: str):
    """An operator takes the call. If Surgeline was still talking, it stops; the operator is on the line."""
    t = _ticket_or_404(ticket_id)
    session = sessions.get(ticket_id)
    if session and not session.done:
        session.done = True
        voice_states.pop(ticket_id, None)
    operator_calls.add(ticket_id)
    return _board_row(t, dispatch.take_over(ticket_id))


# ------------------------------------------------------------------ operator calls (with AI notes)

@app.post("/api/operator/calls")
def start_operator_call(body: StartCall):
    """A call answered by a human operator from the start (Surgeline only takes notes)."""
    ticket = store.create(body.caller_number or fake_caller_number())
    dispatch.call_started(ticket.id)
    dispatch.take_over(ticket.id, "Answered by an operator. Surgeline is taking notes")
    operator_calls.add(ticket.id)
    return {"call_id": ticket.id, "ticket_id": ticket.id, "caller_number": ticket.caller_number}


def _last_line(t, role: str):
    return next((x.text for x in reversed(t.transcript) if x.role == role), None)


@app.post("/api/operator/calls/{call_id}/turn")
async def operator_turn(call_id: str, request: Request, speaker: str = "caller", filename: str = "turn.wav"):
    """One turn of an operator call: raw audio from the operator or the caller. Both sides go through
    speech-to-text for the record and the notes; the caller's turns also fill the ticket, as on AI calls."""
    if speaker not in ("caller", "operator"):
        raise HTTPException(400, "speaker must be caller or operator")
    t = _ticket_or_404(call_id)
    if call_id not in operator_calls:
        raise HTTPException(409, "No operator is on this call")
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "Empty audio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio too large: send one turn, at most 30 seconds")
    stt, _ = _voice_clients()
    other = "operator" if speaker == "caller" else "caller"
    try:
        tr = await stt.transcribe(audio, filename=filename, previous_text=_last_line(t, other))
    except GnaniError as e:
        raise HTTPException(502, f"Speech recognition failed: {e}")
    if not tr.text:
        return {"heard": "", "heard_lang": tr.language, "stt_ms": round(tr.seconds * 1000), "ticket": t.model_dump()}

    turn = Turn(role=speaker, text=tr.text, lang=tr.language)
    t.transcript.append(turn)
    if speaker == "caller":
        asked = _last_line(t, "operator")
        e = await run_in_threadpool(llm.extract, tr.text, f"operator: {asked}" if asked else None,
                                    known_summary(t, t.language))
        heard, _ = judge_turn(tr.language, tr.text, e.spoken_language, e.llm_failed)
        if heard:
            turn.lang = t.language = heard
        apply_extraction(t, e)
        if "rescue" not in t.needs and (t.danger.trapped or t.danger.water_level in ("knee", "waist", "chest", "neck", "roof")):
            t.needs.append("rescue")
        if e.confirmation == "yes" and t.location.locality:
            t.location.confirmed = True
        t.priority, t.priority_reasons, _ = assess(t)
    store.save(t)
    notes.schedule(call_id)
    return {"heard": tr.text, "heard_lang": tr.language, "stt_ms": round(tr.seconds * 1000), "ticket": t.model_dump()}


@app.post("/api/operator/calls/{call_id}/end")
def end_operator_call(call_id: str):
    t = _ticket_or_404(call_id)
    operator_calls.discard(call_id)
    t.call_state = CallState.COMPLETED
    store.save(t)
    notes.schedule(call_id)
    return _board_row(t, dispatch.get(call_id))


class OperatorNotes(BaseModel):
    operator_notes: str = ""


@app.put("/api/tickets/{ticket_id}/notes")
def save_operator_notes(ticket_id: str, body: OperatorNotes):
    _ticket_or_404(ticket_id)
    return notes.save_operator_notes(ticket_id, body.operator_notes)


@app.post("/api/tickets/{ticket_id}/notes/check")
async def check_operator_notes(ticket_id: str, body: OperatorNotes):
    """Compare the operator's notes with what was said in the call. Reports only; changes nothing else."""
    _ticket_or_404(ticket_id)
    return await run_in_threadpool(notes.check, ticket_id, body.operator_notes)


class SimCaller(BaseModel):
    facts: str
    lang: str = "hi-IN"


@app.post("/api/sim/{ticket_id}/caller-reply")
async def simulated_caller_reply(ticket_id: str, body: SimCaller):
    """Demo only: what a simulated caller says next to the operator. text is null if no LLM is configured."""
    _ticket_or_404(ticket_id)
    return {"text": await run_in_threadpool(notes.caller_reply, ticket_id, body.facts, body.lang)}


@app.get("/api/rescuer/{ticket_id}")
def rescuer_view(ticket_id: str):
    """What the assigned team sees on their phone."""
    t = _ticket_or_404(ticket_id)
    row = _board_row(t, dispatch.get(ticket_id))
    row["sms"] = sms_text(row)
    return row


# ------------------------------------------------------------------ pages
# The React app (flood-sos/frontend). In development run `npm run dev` there and open
# http://localhost:5173. After `npm run build`, this server also serves it at http://localhost:8000.
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")