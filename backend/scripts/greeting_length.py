"""How long the greeting (and the waiting-room lines) take to say, with the real Timbre voices.

Design v2, 5.3: the caller should be able to start answering within about 6 seconds of the
greeting starting. Over 7 seconds, cut it.

Run from flood-sos/backend with the venv active (uses a few Gnani credits the first time;
lines already in the voice cache are free):
    python scripts\\greeting_length.py
"""
import asyncio
import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "app" imports work

import httpx  # noqa: E402

from app import phrases, prompts  # noqa: E402
from app.config import settings  # noqa: E402
from app.voice.tts import TimbreTTS  # noqa: E402

LIMIT_S = 7.0
WAITING_ROOM_KEYS = ("p0_wait", "p1_wait", "still_in_line", "request_human_ack", "status_deflect", "one_person")


def seconds(audio: bytes) -> float:
    """Length from the audio bytes themselves. Timbre streams its WAV, so the header's length
    field is a placeholder (it reads as ~134,000 s); only the format fields can be trusted."""
    with wave.open(io.BytesIO(audio)) as w:
        bytes_per_second = w.getframerate() * w.getnchannels() * w.getsampwidth()
    data = audio.find(b"data")
    payload = len(audio) - (data + 8) if data >= 0 else len(audio) - 44
    return payload / float(bytes_per_second)


async def length(tts: TimbreTTS, text: str, lang: str) -> float:
    path = tts.cached_path(text, lang)
    audio = path.read_bytes() if path.exists() else await tts.synthesize(text, lang)
    return seconds(audio)


async def main() -> int:
    if not settings.gnani_api_key:
        print("GNANI_API_KEY is not set in .env")
        return 1
    async with httpx.AsyncClient(timeout=settings.gnani_timeout) as client:
        tts = TimbreTTS(client)
        g = await length(tts, prompts.GREETING["text"], prompts.GREETING["lang"])
        verdict = "OK" if g <= LIMIT_S else f"TOO LONG: cut it to under {LIMIT_S:.0f} s"
        print(f"Greeting: {g:.1f} s  {verdict}\n  {prompts.GREETING['text']}\n")
        langs = [lang for lang in settings.supported_reply_langs if lang in settings.tts_voices]
        print("Waiting-room lines:")
        for key in WAITING_ROOM_KEYS:
            for lang in langs:
                text = phrases.say(key, lang, digits="1 2 3 4")
                print(f"  {key:18} {lang}  {await length(tts, text, lang):4.1f} s")
    return 0 if g <= LIMIT_S else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(asyncio.run(main()))