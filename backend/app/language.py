"""Language handling for a call.

In voice mode, Gnani Prisma (language_code="indic-auto") gives us
`detected_language_code` for each utterance. In text mode we guess from the
script, which is also how Prisma judges it.

The call keeps ONE language and only switches after a sustained change, so a
single English word ("first floor") doesn't flip the whole conversation.
"""
from __future__ import annotations

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


class LanguageTracker:
    """Keeps the call's language stable.

    - The first utterance with at least MIN_WORDS words locks the language.
      Shorter ones ("help! help!") only set a tentative language.
    - After locking, switching needs SWITCH_AFTER consecutive utterances
      in the new language (e.g. the phone is handed to someone else).
    """

    MIN_WORDS = 3
    SWITCH_AFTER = 2

    def __init__(self) -> None:
        self.current: Optional[str] = None
        self.locked = False
        self._pending: Optional[str] = None
        self._pending_count = 0

    def update(self, detected: Optional[str], text: str = "") -> Optional[str]:
        if not detected:
            return self.current
        long_enough = len(text.split()) >= self.MIN_WORDS

        if not self.locked:
            self.current = detected
            self.locked = long_enough
            return self.current

        if detected == self.current:
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
        return "ta-IN", False  # Chennai default until we hear the caller
    if call_lang in settings.supported_reply_langs:
        return call_lang, False
    return settings.fallback_reply_lang, True