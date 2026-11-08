"""Prisma v3.0 speech to text: one REST request per caller turn.

REST (not the WebSocket) because only v3.0 REST detects the language and accepts a list of
expected languages and codemix output. The WebSocket fixes one language per connection.
"""
import json
from dataclasses import dataclass
from typing import Optional

import httpx

from ..config import settings
from .gnani_http import post

MAX_CONTEXT_CHARS = 600  # Prisma keeps only the last 600 characters of previous_text
MAX_KEYTERMS = 200


@dataclass
class Transcript:
    text: str                 # "" when the clip had no speech
    language: Optional[str]   # e.g. "hi-IN"; None when Prisma couldn't judge (empty clip)
    seconds: float            # round trip as seen by us
    server_seconds: Optional[float] = None  # Gnani's end_to_end_latency
    request_id: Optional[str] = None
    truncated: bool = False


class PrismaSTT:
    def __init__(self, client: httpx.AsyncClient, api_key: str = "", *, base_url: str = "",
                 model: str = "", languages: str = "", fmt: str = "",
                 keyterms: Optional[list[str]] = None):
        self.client = client
        self.api_key = api_key or settings.gnani_api_key
        self.url = (base_url or settings.gnani_base_url).rstrip("/") + "/stt/v3"
        self.model = model or settings.stt_model
        self.languages = languages or settings.stt_languages
        self.fmt = fmt or settings.stt_format
        # Area and street names to boost, e.g. from the gazetteer, in English and native script.
        self.keyterms = list(dict.fromkeys(keyterms or []))[:MAX_KEYTERMS]

    async def transcribe(self, audio: bytes, *, filename: str = "turn.wav",
                         previous_text: Optional[str] = None, keyterms: Optional[list[str]] = None,
                         languages: Optional[str] = None) -> Transcript:
        """audio: one caller turn (WAV/MP3/OGG/FLAC/AAC/M4A, 8–44.1 kHz, at most 30 s).
        previous_text: what the agent just asked, so a bare "4" or "naalu" is read in context.
        keyterms / languages: per-call overrides (the call's language first, its script's place names)."""
        data = {"model": self.model, "language_code": languages or self.languages, "format": self.fmt}
        terms = list(dict.fromkeys(keyterms))[:MAX_KEYTERMS] if keyterms is not None else self.keyterms
        if terms:
            data["keyterms"] = json.dumps(terms, ensure_ascii=False)
        if previous_text and previous_text.strip():
            data["previous_text"] = previous_text.strip()[-MAX_CONTEXT_CHARS:]
        r, secs = await post(self.client, "STT", self.url, self.api_key, data=data,
                             files={"audio_file": (filename, audio, "application/octet-stream")})
        body = r.json()
        return Transcript(
            text=(body.get("transcript") or "").strip(),
            language=body.get("detected_language_code"),
            seconds=secs,
            server_seconds=body.get("end_to_end_latency"),
            request_id=body.get("request_id"),
            truncated=bool(body.get("truncated")),
        )
