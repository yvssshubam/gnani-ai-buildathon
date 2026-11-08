"""Timbre v2.5 text to speech, with a disk cache.

Every line callers hear comes from phrases.py, so most replies are the exact same text every
call. Each (voice, language, text) is synthesised once and then served from disk: no credits,
no rate limit, and it plays instantly. Only new text (read-backs, acknowledgements) calls Gnani.
"""
import asyncio
import hashlib
import os
from pathlib import Path
from typing import Iterable, Optional

import httpx

from ..config import settings
from .gnani_http import GnaniError, post


class TimbreTTS:
    def __init__(self, client: httpx.AsyncClient, api_key: str = "", *, base_url: str = "",
                 model: str = "", voices: Optional[dict[str, str]] = None,
                 fallback_lang: str = "", sample_rate: int = 0, speed: float = 0,
                 cache_dir: str = ""):
        self.client = client
        self.api_key = api_key or settings.gnani_api_key
        self.url = (base_url or settings.gnani_base_url).rstrip("/") + "/api/v1/tts/inference"
        self.model = model or settings.tts_model
        self.voices = voices or settings.tts_voices
        self.fallback_lang = fallback_lang or settings.fallback_reply_lang
        self.sample_rate = sample_rate or settings.tts_sample_rate
        self.speed = speed or settings.tts_speed
        self.cache_dir = Path(cache_dir or settings.tts_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, asyncio.Lock] = {}
        self.api_calls = 0   # for the per-call stats line
        self.cache_hits = 0

    def voice_for(self, lang: str) -> tuple[str, str]:
        """(language, voice) to use. A language without a voice falls back, like replies do."""
        if lang in self.voices:
            return lang, self.voices[lang]
        if self.fallback_lang in self.voices:
            return self.fallback_lang, self.voices[self.fallback_lang]
        first = next(iter(self.voices))  # TTS_VOICES has no entry for FALLBACK_REPLY_LANG
        return first, self.voices[first]

    def _key(self, text: str, lang: str, voice: str) -> str:
        raw = "|".join([self.model, voice, lang, str(self.speed), str(self.sample_rate), text])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def cached_path(self, text: str, lang: str) -> Path:
        lang, voice = self.voice_for(lang)
        return self.cache_dir / f"{self._key(text.strip(), lang, voice)}.wav"

    async def synthesize(self, text: str, lang: str) -> bytes:
        """WAV bytes for text in lang. Served from the cache when this exact line was said before."""
        text = text.strip()
        if not text:
            raise ValueError("empty text")
        lang, voice = self.voice_for(lang)
        key = self._key(text, lang, voice)
        path = self.cache_dir / f"{key}.wav"

        # One lock per line, so two parallel calls asking for the same new line pay for it once.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            if path.exists():
                self.cache_hits += 1
                return path.read_bytes()
            body = {
                "text": text, "voice": voice, "model": self.model, "language": lang,
                "speed": self.speed,
                "audio_config": {"sample_rate": self.sample_rate, "num_channels": 1,
                                 "sample_width": 2, "encoding": "linear_pcm", "container": "wav"},
            }
            r, _ = await post(self.client, "TTS", self.url, self.api_key, json=body,
                              headers={"Content-Type": "application/json"})
            self.api_calls += 1
            if not r.headers.get("content-type", "").startswith("audio") or len(r.content) < 44:
                raise GnaniError("TTS", 200, "NOT_AUDIO",
                                 f"got {r.headers.get('content-type')!r}, {len(r.content)} bytes")
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(r.content)
            os.replace(tmp, path)  # atomic: a crash never leaves a half-written cache file
            return r.content

    async def prewarm(self, lines: Iterable[tuple[str, str]]) -> int:
        """Synthesise (text, lang) pairs ahead of the demo, one at a time to respect rate limits.
        Returns how many new lines were generated."""
        before = self.api_calls
        for text, lang in lines:
            if text.strip() and not self.cached_path(text, lang).exists():
                await self.synthesize(text, lang)
        return self.api_calls - before
