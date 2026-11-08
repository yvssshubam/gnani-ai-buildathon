"""Language handling for a call.

In voice mode, Gnani Prisma (language_code="indic-auto") gives us
`detected_language_code` for each utterance. In text mode we guess from the
script, which is also how Prisma judges it.

The call keeps ONE language and only switches after a sustained change, so a
single English word ("first floor") doesn't flip the whole conversation.
"""
from __future__ import annotations

import unicodedata
from typing import Optional

from .config import settings

SCRIPT_RANGES = {
    "ta-IN": (0x0B80, 0x0BFF),
    "te-IN": (0x0C00, 0x0C7F),
    "hi-IN": (0x0900, 0x097F),  # Devanagari (Hindi, Marathi)
    "kn-IN": (0x0C80, 0x0CFF),
    "ml-IN": (0x0D00, 0x0D7F),
    "bn-IN": (0x0980, 0x09FF),
    "gu-IN": (0x0A80, 0x0AFF),
    "pa-IN": (0x0A00, 0x0A7F),
    "or-IN": (0x0B00, 0x0B7F),
}

LANG_NAMES = {
    "ta-IN": "Tamil", "te-IN": "Telugu", "hi-IN": "Hindi", "en-IN": "English",
    "kn-IN": "Kannada", "ml-IN": "Malayalam", "bn-IN": "Bengali", "gu-IN": "Gujarati",
    "pa-IN": "Punjabi", "or-IN": "Odia", "mr-IN": "Marathi",
}


# Hindi / Tamil / Telugu typed in English letters ("hum velachery mein hain", SMS style).
# Only words that are NOT ordinary English words: "he", "main", "do", "to", "par" are left out.
ROMAN_MARKERS = {
    "hi-IN": {
        "hai", "hain", "hoon", "hu", "nahi", "nahin", "nhi", "haan", "haa", "haanji", "ji", "sahi", "galat",
        "paani", "pani", "ghar", "mein", "hum", "hamare", "humare", "hamara", "mera", "meri", "mere", "mujhe",
        "kya", "koi", "kuch", "bhi", "aur", "lekin", "bachao", "madad", "log", "logon", "bahut", "jaldi",
        "abhi", "yahan", "wahan", "kahan", "kitne", "kamar", "ghutne", "ghutna", "chot", "ghayal", "beemar",
        "bimar", "dadi", "nani", "baccha", "bachcha", "bacche", "bachche", "gaya", "gayi", "raha", "rahi",
        "rahe", "tak", "ke", "ki", "ka", "ko", "se", "pe", "wala", "wali", "gali", "makan", "manzil",
        "pata", "theek", "thik", "accha", "achha", "bilkul", "aap", "aapka", "hamein", "chhat",
    },
    "ta-IN": {
        "irukom", "irukkom", "irukku", "iruku", "illa", "illai", "thanni", "thaneer", "veedu", "veetla",
        "veettula", "enga", "naanga", "aama", "aamam", "seri", "romba", "konjam", "vandhu", "varuma",
        "mudiyala", "theriyala", "theriyadhu", "kaapathunga", "kapathunga", "udhavi", "maadi", "mutti",
        "iduppu", "nenju", "paati", "kuzhandhai", "kozhandhai", "thappu", "vayasanavanga", "pakkathula",
    },
    "te-IN": {
        "unnam", "unnamu", "unnaru", "ledu", "kaadu", "avunu", "neellu", "neeru", "illu", "intlo", "memu",
        "ammamma", "nanamma", "sare", "cheppandi", "kapadandi", "sahayam", "mokalu", "mokaali", "nadumu",
        "pilladu", "vachayi", "vachesayi", "perugutunnayi", "teliyadu", "dabba",
    },
}


def detect_roman_language(text: str) -> Optional[str]:
    """Hindi/Tamil/Telugu written in English letters, or None if it reads as English.
    Needs 2+ marker words, or markers making up at least half the words ("nahi galat")."""
    words = [w for w in "".join(c.lower() if c.isalpha() else " " for c in text).split()]
    if not words:
        return None
    hits = {lang: sum(w in markers for w in words) for lang, markers in ROMAN_MARKERS.items()}
    lang = max(hits, key=hits.get)
    n = hits[lang]
    if n == 0 or list(hits.values()).count(n) > 1:     # nothing, or a tie between languages
        return None
    return lang if n >= 2 or n * 2 >= len(words) else None


def detect_script_language(text: str) -> Optional[str]:
    """Guess language from the writing system. Returns None if no letters at all.
    Text in English letters is checked for Hindi/Tamil/Telugu words first (Hinglish, Tanglish)."""
    counts: dict[str, int] = {}
    latin = 0
    for ch in text:
        cp = ord(ch)
        if ch.isascii() and ch.isalpha():
            latin += 1
            continue
        for lang, (lo, hi) in SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if counts:
        # Code-mixed text (Tamil words + English words) counts as the Indian language.
        return max(counts, key=counts.get)
    if not latin:
        return None
    return detect_roman_language(text) or "en-IN"


# What the LLM may answer for spoken_language, mapped to our codes
_LANG_ALIASES = {
    "hi": "hi-IN", "hindi": "hi-IN", "en": "en-IN", "english": "en-IN",
    "ta": "ta-IN", "tamil": "ta-IN", "te": "te-IN", "telugu": "te-IN",
    "kn": "kn-IN", "kannada": "kn-IN", "ml": "ml-IN", "malayalam": "ml-IN",
    "bn": "bn-IN", "bengali": "bn-IN", "gu": "gu-IN", "gujarati": "gu-IN",
    "pa": "pa-IN", "punjabi": "pa-IN", "or": "or-IN", "odia": "or-IN", "mr": "mr-IN", "marathi": "mr-IN",
}


def normalize_lang(value) -> Optional[str]:
    """ "hi", "Hindi", "hi-IN" -> "hi-IN". Anything else -> None."""
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if v in _LANG_ALIASES:
        return _LANG_ALIASES[v]
    code = v.split("-")[0]
    return _LANG_ALIASES.get(code) if code in _LANG_ALIASES else None


def judge_turn(stt_lang: Optional[str], text: str, spoken: Optional[str],
               llm_failed: bool = False) -> tuple[Optional[str], bool]:
    """Which language this caller turn is in, and whether we're sure.

    Prisma's tag can be wrong in a way the letters can't catch: Hindi speech written in Tamil
    letters, tagged ta-IN. So the LLM, which reads the words, also says which language they are
    ("முஜே பச்சாவோ" is "mujhe bachao": Hindi). Its answer wins when they disagree, but only a
    turn where the speech tag (or, for typed text, the letters) and the LLM agree is "sure".
    Only a sure turn can switch the call at once; anything else needs two turns in a row.
    """
    observed = stt_lang or detect_script_language(text)
    if spoken:
        return spoken, spoken == observed
    # No LLM verdict. Typed text: the letters are reliable.
    if stt_lang is None:
        return observed, True
    # Speech, and the LLM failed: Prisma's tag matching the letters it wrote is the best we have.
    # (If that was wrong, the next turn can switch back: requests to Prisma no longer lean
    # toward the call's language.) A quick-parsed short reply: the tag alone is not enough.
    return observed, llm_failed and observed == detect_script_language(text)


def letter_count(text: str) -> int:
    """Characters that aren't spaces, punctuation or symbols (vowel signs count, so Telugu,
    Tamil and Hindi are measured fairly)."""
    return sum(1 for c in text if unicodedata.category(c)[0] not in "PZS")


def is_full_sentence(text: str, words: int, letters: int) -> bool:
    """By words OR letters: Telugu and Tamil say a whole sentence in few, long words
    ("లేదు, ఎవరికీ తగలలేదు" = "no, nobody got hurt" is 3 words but 17 letters)."""
    return len(text.split()) >= words or letter_count(text) >= letters


class LanguageTracker:
    """Keeps the call's language stable.

    - The first utterance with at least MIN_WORDS words (or MIN_LETTERS letters) locks the language.
      Shorter ones ("help! help!") only set a tentative language.
    - After locking, a full sentence (SWITCH_WORDS+ words or SWITCH_LETTERS+ letters) in another
      language switches at once,
      if we're sure of its language (see judge_turn): the caller changed language, or the phone
      was handed to someone else.
    - Short replies ("no", "ok", "haan"), and sentences whose language we're not sure of, need
      SWITCH_AFTER in a row, so one stray word or one wrong guess doesn't flip the whole call.
    """

    MIN_WORDS = 3
    MIN_LETTERS = 10
    SWITCH_WORDS = 4
    SWITCH_LETTERS = 12   # "ok thank you" is 10, so stray English replies still need two in a row
    SWITCH_AFTER = 2

    def __init__(self) -> None:
        self.current: Optional[str] = None
        self.locked = False
        self._pending: Optional[str] = None
        self._pending_count = 0

    def update(self, detected: Optional[str], text: str = "", sure: bool = True) -> Optional[str]:
        if not detected:
            return self.current
        long_enough = is_full_sentence(text, self.MIN_WORDS, self.MIN_LETTERS)

        if not self.locked:
            self.current = detected
            self.locked = long_enough
            return self.current

        if detected == self.current:
            self._pending, self._pending_count = None, 0
            return self.current

        if sure and is_full_sentence(text, self.SWITCH_WORDS, self.SWITCH_LETTERS):
            self.current = detected
            self._pending, self._pending_count = None, 0
            return self.current

        if detected == self._pending:
            self._pending_count += 1
        else:
            self._pending, self._pending_count = detected, 1

        if self._pending_count >= self.SWITCH_AFTER:
            self.current = detected
            self._pending, self._pending_count = None, 0
        return self.current


def reply_language(call_lang: Optional[str]) -> tuple[str, bool]:
    """Language we answer in, and whether an interpreter is needed."""
    if call_lang is None:
        return settings.fallback_reply_lang, False  # until we hear the caller
    if call_lang in settings.supported_reply_langs:
        return call_lang, False
    return settings.fallback_reply_lang, True