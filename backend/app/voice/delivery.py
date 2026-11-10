"""How each spoken part is delivered: its pace, how digits are said, and (on Timbre v3.0) its tags.

Timbre v2.5 has no emotion control. Every fixed line was made once, at one speed, so "your case
is most urgent" and "please say that again" came out in the same even tone. Tone on this line
comes from three things we do control:

  1. the words (phrases.py, reviewed),
  2. the pace of each kind of line (below), and
  3. on Timbre v3.0 only, an optional audio tag per kind of line (TTS_TAGS).

Kinds of line ("styles"):
  plain     questions and acknowledgements
  steady    instructions, closing lines, "you're in line": a little slower, so they land
  brisk     "most urgent, an officer is being alerted": a little quicker and firmer
  readback  the details being read back (people, address, PIN): slowest, so they can be checked

What the caller sees in the transcript doesn't change: this only shapes the audio.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from .. import phrases
from ..config import settings

# phrase key -> style. Anything not listed is "plain".
STYLE_OF_KEY = {
    "calm": "steady", "not_heard": "steady", "one_person": "steady", "again": "steady",
    "anger_ack": "steady", "ans_when_help": "steady", "status_deflect": "steady",
    "ans_stay_or_move": "steady", "ans_electricity": "steady", "ans_animal": "steady",
    "handoff": "steady", "p1_wait": "steady", "still_in_line": "steady",
    "close": "steady", "close_callback": "steady",
    "urgent": "brisk", "p0_wait": "brisk",
}

# Lines short enough that a long pause after them sounds like the agent lost its place.
SHORT_KEYS = {"ack", "noted", "go_ahead", "again", "rephrase"}

DIGIT_WORDS = {
    "en-IN": "zero one two three four five six seven eight nine".split(),
    "hi-IN": "ज़ीरो एक दो तीन चार पाँच छह सात आठ नौ".split(),
    "te-IN": "సున్నా ఒకటి రెండు మూడు నాలుగు ఐదు ఆరు ఏడు ఎనిమిది తొమ్మిది".split(),
    # everyday spoken Tamil, to match the rest of the Tamil lines (needs a Tamil speaker's check)
    "ta-IN": "ஜீரோ ஒண்ணு ரெண்டு மூணு நாலு அஞ்சு ஆறு ஏழு எட்டு ஒம்பது".split(),
}
SENTENCE_END = {"hi-IN": "।"}   # every other language ends with "."

# "4 7 2 1", "5 0 0 0 9 4": the ticket number and PIN, already spaced out by the dialogue engine
SPACED_DIGITS = re.compile(r"(?<![\d.])\d(?: \d){2,}(?!\d|\.\d)")


@dataclass(frozen=True)
class Piece:
    text: str       # exactly what Timbre is sent
    speed: float
    gap_ms: int     # silence after this piece, when another piece follows
    fixed: bool = True   # the same text on every call (so scripts/prewarm_voice.py can make it ahead)


def _setting_map(raw: str) -> dict[str, str]:
    return {k.strip(): v.strip() for k, v in (p.split(":", 1) for p in raw.split(",") if ":" in p)}


def speed_for(style: str) -> float:
    pace = _setting_map(settings.tts_pace)
    try:
        factor = float(pace.get(style, pace.get("plain", "1.0")))
    except ValueError:
        factor = 1.0
    # Timbre accepts 0.85 to 1.15
    return round(min(1.15, max(0.85, settings.tts_speed * factor)), 2)


def tag_for(style: str, model: str) -> str:
    """Audio tag for this style. Only Timbre v3.0 understands tags (v2.5 strips them, but they'd
    still change the cache key), so on any other model this is always empty."""
    if not model.startswith("timbre-v3"):
        return ""
    return _setting_map(settings.tts_tags).get(style, "")


def digits_as_words(text: str, lang: str) -> str:
    """'4 7 2 1' -> 'four seven, two one'. Timbre's docs ask for numbers written as words, and
    grouping them (2+2 for the ticket, 3+3 for a PIN) gives the listener a beat to catch up."""
    words = DIGIT_WORDS.get(lang, DIGIT_WORDS["en-IN"])

    def say(m: re.Match) -> str:
        ds = m.group(0).split()
        size = 2 if len(ds) == 4 else 3
        groups = [ds[i:i + size] for i in range(0, len(ds), size)]
        return ", ".join(" ".join(words[int(d)] for d in g) for g in groups)
    return SPACED_DIGITS.sub(say, text)


@lru_cache(maxsize=None)
def _index(lang: str) -> tuple[dict[str, str], list[tuple[re.Pattern, str]]]:
    """Fixed lines by exact text, and templated lines ({digits}, {details}) as patterns."""
    exact: dict[str, str] = {}
    templates: list[tuple[re.Pattern, str]] = []
    for key, text in phrases.PHRASES.get(lang, {}).items():
        if "{" not in text:
            exact.setdefault(text.strip(), key)
        else:
            pattern = re.escape(text.strip())
            pattern = re.sub(r"\\\{(\w+)\\\}", r"(?P<\1>.+?)", pattern)
            templates.append((re.compile(f"^{pattern}$", re.S), key))
    return exact, templates


def key_of(part: str, lang: str) -> tuple[str, re.Match | None]:
    """Which phrase this spoken part is ("" if it isn't one, like an LLM acknowledgement)."""
    exact, templates = _index(lang)
    part = part.strip()
    if part in exact:
        return exact[part], None
    for pattern, key in templates:
        m = pattern.match(part)
        if m:
            return key, m
    return "", None


def _end(text: str, lang: str) -> str:
    text = text.strip().rstrip(":,;").strip()
    if text and text[-1] not in "।.?!":
        text += SENTENCE_END.get(lang, ".")
    return text


def _readback_pieces(lang: str, details: str, model: str, gap: int) -> list[Piece]:
    """'Let me check: {details}. Is that correct?' as three pieces: the intro and the question
    are fixed (cached once), the details are slowed down and given room on either side."""
    template = phrases.PHRASES.get(lang, phrases.PHRASES["en-IN"])["readback"]
    before, _, after = template.partition("{details}")
    out = []
    if before.strip():
        out.append(Piece(_end(before, lang), speed_for("plain"), gap * 2 // 3))
    tag = tag_for("readback", model)
    body = _end(digits_as_words(details, lang), lang)
    out.append(Piece(f"{tag} {body}".strip(), speed_for("readback"), gap + gap // 4, fixed=False))
    after = after.strip().lstrip("।.,:;").strip()
    if after:
        out.append(Piece(after, speed_for("plain"), gap))
    return out


def pieces(part: str, lang: str, model: str = "") -> list[Piece]:
    """The pieces Timbre is asked for, for one part of a reply."""
    model = model or settings.tts_model
    gap = settings.tts_gap_ms
    key, m = key_of(part, lang)
    if key == "readback" and m:
        return _readback_pieces(lang, m.group("details"), model, gap)
    style = STYLE_OF_KEY.get(key, "plain")
    tag = tag_for(style, model)
    text = f"{tag} {digits_as_words(part.strip(), lang)}".strip()
    short = key in SHORT_KEYS or (not key and len(part.split()) <= 2)
    return [Piece(text, speed_for(style), gap // 2 if short else gap)]


def fixed_pieces(langs: list[str], extra: list[tuple[str, str]] | None = None,
                 model: str = "") -> list[tuple[str, str, float]]:
    """Every piece that is the same on every call, as (text, lang, speed), for scripts/prewarm_voice.py:
    the fixed lines, plus the fixed intro and question around each language's read-back."""
    out: list[tuple[str, str, float]] = []
    for text, lang in extra or []:
        out += [(p.text, lang, p.speed) for p in pieces(text, lang, model)]
    for lang in langs:
        for key, text in phrases.PHRASES.get(lang, {}).items():
            if key == "readback":
                rb = _readback_pieces(lang, "-", model, settings.tts_gap_ms)
                out += [(p.text, lang, p.speed) for p in rb if p.fixed]
            elif "{" not in text and key not in READBACK_PIECES:
                out += [(p.text, lang, p.speed) for p in pieces(text, lang, model)]
    return list(dict.fromkeys(out))


# phrases.py keys that are pieces of the read-back sentence, never spoken on their own
READBACK_PIECES = {"people", "person", "including", "at", "near", "door", "floor_n",
                   "ground", "terrace", "none", "sep", "pin"}
