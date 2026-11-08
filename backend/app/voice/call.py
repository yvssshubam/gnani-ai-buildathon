"""One voice turn: caller audio -> Prisma -> CallSession.handle (Phase 1, unchanged) -> Timbre audio.

The reply is spoken part by part (acknowledgement, calming line, answer, next question), and
each part is its own cached audio file. Fixed parts are free after the first call.
"""
from __future__ import annotations

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

# phrases.py keys that are pieces of the read-back sentence, never spoken on their own
READBACK_PIECES = {"people", "person", "including", "at", "near", "door", "floor_n",
                   "ground", "terrace", "none", "sep"}


# Script of each language's own letters, to pick that language's place names
_SCRIPTS = {"ta-IN": (0x0B80, 0x0BFF), "te-IN": (0x0C00, 0x0C7F), "hi-IN": (0x0900, 0x097F)}


def _in_script(word: str, lang: str) -> bool:
    lo, hi = _SCRIPTS[lang]
    return any(lo <= ord(c) <= hi for c in word)


def keyterms(lang: Optional[str] = None) -> list[str]:
    """Area names to boost in speech recognition. Always the English spellings; names in another
    script only once the call is in that language. Sending Tamil-script names on every request
    pushed Prisma to write Hindi speech in Tamil letters."""
    terms: list[str] = []
    for loc in LOCALITIES:
        terms.append(loc["name"])
        terms.extend(a for a in loc["aliases"] if a.isascii() or (lang in _SCRIPTS and _in_script(a, lang)))
    return list(dict.fromkeys(terms))[:200]


def languages_for(lang: Optional[str]) -> str:
    """The language hints for Prisma, with the call's language first once it's known."""
    hints = [x.strip() for x in settings.stt_languages.split(",") if x.strip()]
    if lang and lang in hints:
        hints = [lang] + [x for x in hints if x != lang]
    return ",".join(hints[:4])


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
    last_agent_text: Optional[str] = None
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
    lang = getattr(getattr(session, "ticket", None), "language", None)
    tr = await stt.transcribe(audio, filename=filename, previous_text=state.last_agent_text,
                              keyterms=keyterms(lang), languages=languages_for(lang))

    if not tr.text:
        # Silence, wind, rain: don't count it as a turn and don't call the LLM. Ask again.
        state.not_heard_in_a_row += 1
        reply = phrases.say("not_heard", state.reply_lang)
        result = {"reply": reply, "reply_parts": [reply], "reply_lang": state.reply_lang,
                  "action": "not_heard", "done": False, "ticket": session.ticket.model_dump()}
    else:
        state.not_heard_in_a_row = 0
        # handle() may call the LLM (blocking HTTP): run it off the event loop
        result = await run_in_threadpool(session.handle, tr.text, tr.language)
        state.reply_lang = result.get("reply_lang") or state.reply_lang

    parts = result.get("reply_parts") or ([result["reply"]] if result.get("reply") else [])
    urls, tts_ms, tts_error = await speak(tts, parts, result["reply_lang"])
    if result.get("reply"):
        state.last_agent_text = result["reply"]

    result.update({
        "heard": tr.text,
        "heard_lang": tr.language,
        "stt_ms": round(tr.seconds * 1000),
        "tts_ms": tts_ms,
        "audio": urls,
        "not_heard_in_a_row": state.not_heard_in_a_row,
    })
    if tts_error:
        result["tts_error"] = tts_error
    return result
