"""One voice turn: caller audio -> Prisma -> CallSession.handle (Phase 1, unchanged) -> Timbre audio.

The reply is spoken part by part (acknowledgement, calming line, answer, next question), and
each part is its own cached audio file. Fixed parts are free after the first call.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from starlette.concurrency import run_in_threadpool

from .. import phrases
from ..config import settings
from ..gazetteer import LOCALITIES
from .gnani_http import GnaniError
from .stt import PrismaSTT
from .tts import TimbreTTS

AUDIO_ROUTE = "/api/voice/audio/"
PLACE_WAIT_SECONDS = 3.0   # longest a turn waits for an off-map area's map lookup

# phrases.py keys that are pieces of the read-back sentence, never spoken on their own
READBACK_PIECES = {"people", "person", "including", "at", "near", "door", "floor_n",
                   "ground", "terrace", "none", "sep"}


# Every request to Prisma is the same whatever language the call is in: the same language hints
# in the same order (STT_LANGUAGES), English place names only, and the agent's question in
# English as context. Shaping them by the call's language (that language first, its script's
# place names, the agent's line in its script) made one wrong guess stick: once Prisma wrote
# Hindi in Tamil letters, every later request pushed it further toward Tamil, and the caller
# could no longer switch language.


def keyterms() -> list[str]:
    """Area names to boost in speech recognition, English spellings only."""
    terms: list[str] = []
    for loc in LOCALITIES:
        terms.append(loc["name"])
        terms.extend(a for a in loc["aliases"] if a.isascii())
    return list(dict.fromkeys(terms))[:200]


def stt_context(question_en: Optional[str]) -> Optional[str]:
    """The previous_text for Prisma: the agent's last question in English, or nothing
    (STT_CONTEXT=none) if English context ever pulls Indian-language answers into English letters."""
    return question_en if settings.stt_context == "question_en" else None


def fixed_lines(langs: list[str], extra: Optional[list[tuple[str, str]]] = None) -> list[tuple[str, str]]:
    """Every complete line in phrases.py that never changes (no {placeholders}), as (text, lang)."""
    out = list(extra or [])
    for lang in langs:
        for key, text in phrases.PHRASES.get(lang, {}).items():
            if key not in READBACK_PIECES and "{" not in text:
                out.append((text, lang))
    return out


@dataclass
class VoiceState:
    """What the voice layer remembers per call (the dialogue engine keeps everything else)."""
    reply_lang: str
    last_agent_text: Optional[str] = None   # the agent's last question, in English (STT context)
    not_heard_in_a_row: int = 0


async def speak(tts: TimbreTTS, parts: list[str], lang: str) -> tuple[list[Optional[str]], int, Optional[str]]:
    """Audio URL per part (None if that part failed), milliseconds, first error.
    A TTS failure never ends the call: the browser shows the text instead."""
    started = time.perf_counter()
    urls: list[Optional[str]] = []
    error = None
    for part in parts:
        if not part.strip():
            continue
        try:
            await tts.synthesize(part, lang)
            urls.append(AUDIO_ROUTE + tts.cached_path(part, lang).name)
        except GnaniError as e:
            urls.append(None)
            error = error or str(e)
    return urls, round((time.perf_counter() - started) * 1000), error


async def voice_turn(session, state: VoiceState, audio: bytes, filename: str,
                     stt: PrismaSTT, tts: TimbreTTS) -> dict:
    """Raises GnaniError if speech recognition fails (the caller should be asked to repeat)."""
    tr = await stt.transcribe(audio, filename=filename, previous_text=stt_context(state.last_agent_text))

    waiting = bool(getattr(session, "waiting", False))
    if not tr.text:
        # Silence, wind, rain: don't count it as a turn and don't call the LLM. Ask again; the
        # second time in a row, ask for one person close to the phone (design v2, 8.4). A caller
        # waiting in line for an officer isn't asked anything: the reassurance timer covers them.
        state.not_heard_in_a_row += 1
        if waiting:
            reply = ""
        elif state.not_heard_in_a_row == 2:
            reply = phrases.say("one_person", state.reply_lang)
        else:
            reply = phrases.say("not_heard", state.reply_lang)
        result = {"reply": reply, "reply_parts": [reply] if reply else [], "reply_lang": state.reply_lang,
                  "action": "not_heard", "done": False, "waiting": waiting,
                  "reassure": phrases.say("still_in_line", state.reply_lang) if waiting else None,
                  "ticket": session.ticket.model_dump()}
    else:
        state.not_heard_in_a_row = 0
        if hasattr(session, "place_in_turn"):
            session.place_in_turn = True   # an off-map area is looked up while the reply is spoken
        # handle() may call the LLM (blocking HTTP): run it off the event loop
        result = await run_in_threadpool(session.handle, tr.text, tr.language)
        state.reply_lang = result.get("reply_lang") or state.reply_lang

    parts = result.get("reply_parts") or ([result["reply"]] if result.get("reply") else [])
    if getattr(session, "area_to_place", False):
        # "Sainikpuri, 500094": find it on OpenStreetMap at the same time as the reply is spoken, so
        # the pin is on this turn's ticket. If the lookup is slow it carries on and saves the pin later.
        speech = asyncio.ensure_future(speak(tts, parts, result["reply_lang"]))
        lookup = asyncio.get_running_loop().run_in_executor(None, session.place_area)
        try:
            await asyncio.wait_for(asyncio.shield(lookup), timeout=PLACE_WAIT_SECONDS)
        except asyncio.TimeoutError:
            pass
        urls, tts_ms, tts_error = await speech
        result["ticket"] = session.ticket.model_dump()
    else:
        urls, tts_ms, tts_error = await speak(tts, parts, result["reply_lang"])
    if result.get("reply"):
        question = getattr(session, "question_en", None)
        state.last_agent_text = question() if callable(question) else None

    result.update({
        "heard": tr.text,
        "heard_lang": tr.language,
        "stt_ms": round(tr.seconds * 1000),
        "tts_ms": tts_ms,
        "audio": urls,
        "not_heard_in_a_row": state.not_heard_in_a_row,
    })
    if result.get("waiting") and result.get("reassure"):
        # "You're still in line": the browser plays it after ~40 s of quiet (silence makes people hang up)
        reassure_urls, _, _ = await speak(tts, [result["reassure"]], result["reply_lang"])
        result["reassure_audio"] = reassure_urls
    if tts_error:
        result["tts_error"] = tts_error
    return result