"""Join the parts of one reply into a single WAV, with the silence between them set by us.

Each part of a reply ("Okay.", the calming line, the next question) is its own cached Timbre
clip. Played one after another in the browser, every gap was: the end of one clip's own
silence, a new audio fetch and decode, and the start of the next clip's own silence. That came
to most of a second between "Okay." and the question, which is what made the agent sound
halting. Here each clip's leading and trailing silence is cut down to a short natural pad, and
the parts are joined with a fixed gap, so the reply plays as one even piece of speech.

Plain standard library: no numpy, so it runs the same on Windows and in tests.
"""
from __future__ import annotations

import io
import wave
from array import array
from dataclasses import dataclass
from typing import Optional

FRAME_MS = 10          # silence is judged 10 ms at a time
LEAD_PAD_MS = 30       # keep this much before the first sound, so the first consonant isn't clipped
TAIL_PAD_MS = 80       # and this much after the last, so a soft final syllable fades out naturally
FADE_MS = 6            # tiny fade at every cut, so there is no click


@dataclass
class Clip:
    rate: int
    samples: array      # 16-bit mono PCM


class CantStitch(ValueError):
    """The audio isn't 16-bit mono WAV at one sample rate. The caller falls back to separate clips."""


def read_wav(data: bytes) -> Clip:
    try:
        with wave.open(io.BytesIO(data)) as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise CantStitch(f"{w.getsampwidth() * 8}-bit, {w.getnchannels()} channels")
            rate = w.getframerate()
            raw = w.readframes(w.getnframes())
    except (wave.Error, EOFError) as e:
        raise CantStitch(str(e)) from e
    samples = array("h")
    samples.frombytes(raw)
    return Clip(rate, samples)


def write_wav(clip: Clip) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(clip.rate)
        w.writeframes(clip.samples.tobytes())
    return out.getvalue()


def _loud_frames(samples: array, frame: int, threshold: int) -> list[bool]:
    return [max(map(abs, samples[i:i + frame]), default=0) >= threshold
            for i in range(0, len(samples), frame)]


def trim(clip: Clip) -> Clip:
    """Cut the clip's own leading and trailing silence down to a short pad."""
    s = clip.samples
    if not s:
        return clip
    peak = max(map(abs, s)) or 1
    frame = max(1, clip.rate * FRAME_MS // 1000)
    # A sound starts sharper than it ends: a stricter threshold at the start, a gentler one at
    # the end, so breathy last syllables ("है", "ఉన్నారా") aren't cut off.
    start_loud = _loud_frames(s, frame, max(200, peak // 20))
    end_loud = _loud_frames(s, frame, max(120, peak // 50))
    if not any(start_loud):
        return clip
    first = start_loud.index(True) * frame
    last = (len(end_loud) - end_loud[::-1].index(True)) * frame
    a = max(0, first - clip.rate * LEAD_PAD_MS // 1000)
    b = min(len(s), last + clip.rate * TAIL_PAD_MS // 1000)
    out = array("h", s[a:b])
    fade = min(len(out) // 2, clip.rate * FADE_MS // 1000)
    for i in range(fade):
        k = i / fade
        out[i] = int(out[i] * k)
        out[-1 - i] = int(out[-1 - i] * k)
    return Clip(clip.rate, out)


def join(wavs: list[bytes], gaps_ms: list[int]) -> bytes:
    """One WAV: each clip trimmed, then gaps_ms[i] of silence after clip i (the last gap is unused)."""
    if not wavs:
        raise CantStitch("nothing to join")
    clips = [trim(read_wav(w)) for w in wavs]
    rate = clips[0].rate
    if any(c.rate != rate for c in clips):
        raise CantStitch("clips have different sample rates")
    out = array("h")
    for i, c in enumerate(clips):
        out.extend(c.samples)
        if i < len(clips) - 1:
            gap = gaps_ms[i] if i < len(gaps_ms) else 0
            out.extend([0] * (rate * gap // 1000))
    return write_wav(Clip(rate, out))


def duration_ms(data: bytes) -> Optional[int]:
    try:
        c = read_wav(data)
    except CantStitch:
        return None
    return len(c.samples) * 1000 // c.rate
