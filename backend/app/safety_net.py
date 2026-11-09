"""The plainest facts, read by rule, for when the LLM call fails.

A Groq error (rate limit, timeout, bad JSON) used to lose the whole turn: "किसी को चोट नहीं लगी,
पर पानी तेज़ी से बढ़ रहा है" was thrown away and the caller was asked about injuries again.
This only runs when the LLM failed, so it never changes a normal turn. It reads only: nobody hurt,
someone hurt, water rising, who is with them (elderly, child, baby, pregnant, sick), and the number
of people, that last one only as the answer to "how many people?". Each sentence part is read on
its own, so "nobody hurt, but the water is rising" gives both.
"""
from __future__ import annotations

import re

from .quick_parse import NUMBER_WORDS

# split "nobody hurt, but water rising" into parts
_PARTS = re.compile(r"[,.;!?।|]|\b(?:but|par|lekin|magar)\b|\s(?:पर|लेकिन|मगर|కానీ|ஆனா|ஆனால்)\s", re.IGNORECASE)

NOBODY_HURT = [
    r"(?:किसी को|कोई)\s*(?:भी\s*)?(?:चोट\s*नहीं|घायल\s*नहीं)", r"चोट\s*नहीं\s*(?:लगी|आई)", r"कोई\s*घायल\s*नहीं",
    r"\b(?:kisi ko|koi)\s*(?:bhi\s*)?(?:chot|ghayal)\s*nahi", r"\bchot\s*nahi\s*lagi",
    r"\bno\s*(?:one|body)\s*(?:is\s*|got\s*|was\s*)?(?:hurt|injured)", r"\bnobody\s*(?:is\s*)?(?:hurt|injured)",
    r"\bno\s*injur", r"\bnot\s*(?:hurt|injured)",
    r"ఎవరికీ\s*దెబ్బ(?:లు)?\s*(?:తగల్లేదు|తగలలేదు|లేవు)", r"దెబ్బ(?:లు)?\s*(?:తగల్లేదు|తగలలేదు)", r"గాయాలు\s*లేవు",
    r"யாருக்கும்\s*(?:அடி|காயம்)\s*(?:படல|இல்ல|இல்லை)", r"காயம்\s*(?:இல்ல|இல்லை)",
]
SOMEONE_HURT = [
    r"चोट\s*लगी", r"घायल\s*(?:है|हैं|हो)", r"\bchot\s*lagi", r"\bghayal\s*(?:hai|hain)",
    r"\b(?:is|are|got|been)\s*(?:badly\s*)?(?:hurt|injured)", r"\binjured\b",
    r"దెబ్బ(?:లు)?\s*(?:తగిలింది|తగిలాయి|తగిలాయ్)", r"గాయ(?:ం|ాలు)\s*(?:అయింది|అయ్యాయి)",
    r"அடி\s*(?:பட்டிருக்கு|பட்டுச்சு|பட்டது)", r"காயம்\s*(?:ஆயிருக்கு|ஆச்சு)",
]
NEGATION = re.compile(r"नहीं|नही|\bnahi\b|\bnahin\b|\bno\b|\bnot\b|\bnobody\b|లేదు|లేవు|తగల్లేదు|இல்ல|இல்லை|படல", re.IGNORECASE)
WATER_RISING = [
    r"पानी\s*(?:\S+\s*){0,3}बढ़\s*रहा", r"\bpani\s*(?:\S+\s*){0,3}badh\s*raha", r"\bpaani\s*(?:\S+\s*){0,3}badh\s*raha",
    r"\bwater\s*(?:is\s*)?(?:\S+\s*){0,2}(?:rising|going\s*up|increasing|coming\s*up)",
    r"నీళ్ళు\s*(?:\S+\s*){0,2}పెరుగుతున్నా", r"నీళ్లు\s*(?:\S+\s*){0,2}పెరుగుతున్నా", r"నీరు\s*(?:\S+\s*){0,2}పెరుగుతో",
    r"தண்ணி\s*(?:\S+\s*){0,2}ஏறி", r"தண்ணீர்\s*(?:\S+\s*){0,2}(?:ஏறி|அதிகமா)",
]


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def danger_by_rule(text: str) -> dict:
    """{"injured": False/True, "water_rising": True}, only for what the caller plainly said."""
    found: dict = {}
    sentences = re.findall(r"[^?।.!]+[?।.!]?", text or "")
    parts = [p for s in sentences if not s.strip().endswith("?")   # a question isn't a statement
             for p in _PARTS.split(s)]
    for part in parts:
        part = (part or "").strip()
        if not part:
            continue
        if _any(NOBODY_HURT, part):
            found.setdefault("injured", False)
        elif _any(SOMEONE_HURT, part) and not NEGATION.search(part):
            found["injured"] = True
        if _any(WATER_RISING, part) and not NEGATION.search(part):
            found["water_rising"] = True
    return found


VULNERABLE = {
    "elderly": [r"दादी", r"नानी", r"दादा", r"नाना", r"बुज़ुर्ग", r"बुजुर्ग", r"\bdadi\b", r"\bnani\b",
                r"grand(?:mother|father|ma|pa)", r"\bold (?:man|woman|lady|people)", r"\belderly\b",
                r"అమ్మమ్మ", r"నానమ్మ", r"తాతయ్య", r"\bతాత", r"ముసలి", r"பாட்டி", r"தாத்தா", r"வயசானவ"],
    "infant": [r"छोटा बच्चा", r"\bbaby\b", r"\binfant\b", r"చంటి", r"పసి", r"கைக்குழந்தை"],
    "child": [r"बच्च", r"\bbacch?[ae]\b", r"\bchild", r"\bkids?\b", r"పిల్ల", r"குழந்த", r"பசங்க"],
    "pregnant": [r"प्रेग्नेंट", r"गर्भवती", r"pregnant", r"ప్రెగ్నెంట్", r"గర్భిణి", r"கர்ப்ப"],
    "sick": [r"बीमार", r"\bsick\b", r"\bill\b", r"\bbimar\b", r"అనారోగ్య", r"ఒంట్లో బాగా లేదు", r"బాగోలేదు",
             r"உடம்பு சரியில்ல"],
}
# Telugu "we four" forms ("మేము నలుగురం")
PEOPLE_WORDS = {**{k: v for k, v in NUMBER_WORDS.items() if " " not in k},
                "ఇద్దరం": 2, "ముగ్గురం": 3, "నలుగురం": 4, "ఐదుగురం": 5, "ఆరుగురం": 6}
_TOKENS = re.compile(r"[^\s,.;!?।|]+")


def people_by_rule(text: str):
    """The number in an answer to "how many people?", if there is exactly one ("मेरे साथ चार लोग")."""
    values = set()
    for tok in _TOKENS.findall((text or "").lower()):
        if tok.isdigit() and len(tok) <= 2:
            values.add(int(tok))
        elif tok in PEOPLE_WORDS:
            values.add(PEOPLE_WORDS[tok])
    values.discard(0)
    return values.pop() if len(values) == 1 else None


def facts_by_rule(text: str, asked_slot=None) -> dict:
    """Everything above that the caller plainly said. asked_slot: the slot we just asked about."""
    found = danger_by_rule(text)
    sentences = re.findall(r"[^?।.!]+[?।.!]?", text or "")
    parts = [p.strip() for s in sentences if not s.strip().endswith("?") for p in _PARTS.split(s) if p and p.strip()]
    who = []
    for kind, patterns in VULNERABLE.items():
        if any(_any(patterns, p) and not NEGATION.search(p) for p in parts):
            if not (kind == "child" and "infant" in who):
                who.append(kind)
    if who:
        found["vulnerable"] = who
    if asked_slot == "people":
        n = people_by_rule(text)
        if n:
            found["people_count"] = n
    return found