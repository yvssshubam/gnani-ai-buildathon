"""Answer short replies WITHOUT calling the LLM.

When we just asked "how many people?" and the caller says "நாலு" or "4",
plain code can understand it. That saves an API call, tokens and ~1 second.

Only very short, unambiguous replies are handled here. Anything longer or
unclear goes to the LLM as before.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .gazetteer import clean_pincode
from .models import Extraction

MAX_WORDS = 4

NUMBER_WORDS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "alone": 1, "only me": 1, "just me": 1,
    # Tamil
    "ஒண்ணு": 1, "ஒன்று": 1, "ஒருத்தர்": 1, "நான் மட்டும்": 1, "ரெண்டு": 2, "இரண்டு": 2, "மூணு": 3, "மூன்று": 3,
    "ஒரு": 1, "நாலு": 4, "நான்கு": 4, "அஞ்சு": 5, "ஐந்து": 5, "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
    # Hindi
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10, "अकेला": 1, "अकेली": 1,
    # Telugu
    "ఒకటి": 1, "ఒక్కరు": 1, "రెండు": 2, "ఇద్దరు": 2, "మూడు": 3, "ముగ్గురు": 3, "నాలుగు": 4, "నలుగురు": 4,
    "ఐదు": 5, "ఐదుగురు": 5, "ఆరు": 6, "ఏడు": 7, "ఎనిమిది": 8, "తొమ్మిది": 9, "పది": 10,
    # Hindi / Tamil / Telugu in English letters ("do log hain", "naalu per")
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "saat": 7,
    "aath": 8, "nau": 9, "das": 10, "akela": 1, "akeli": 1,
    "onnu": 1, "rendu": 2, "moonu": 3, "naalu": 4, "anju": 5, "aaru": 6, "ezhu": 7, "ettu": 8, "pathu": 10,
    "okati": 1, "iddaru": 2, "mugguru": 3, "naluguru": 4, "aiduguru": 5,
}

# Words allowed around a number in a "how many people?" answer. Anything else -> LLM.
PEOPLE_FILLER = {"only", "just", "me", "people", "persons", "person", "of", "us", "we", "are", "here", "total", "members",
                 "பேர்", "பேரு", "இருக்கோம்", "இருக்கோம்.", "மொத்தம்", "நாங்க",
                 "लोग", "हैं", "हम", "कुल", "जने",
                 "మంది", "ఉన్నాం", "ఉన్నాము", "మేము", "మొత్తం",
                 "log", "hain", "hai", "hum", "kul", "jane", "log hain",
                 "per", "peru", "irukom", "irukkom", "naanga", "mandi", "unnam", "memu"}

YES = ["yes", "yeah", "yep", "correct", "right", "ok", "okay", "sari", "aama", "ama", "haan",
       "haa", "ha", "haanji", "hanji", "ji", "sahi", "theek", "thik", "bilkul", "seri", "aamam", "avunu", "sare",
       "ஆமா", "ஆமாம்", "சரி", "கரெக்ட்", "ஆம்",
       "हाँ", "हां", "जी", "सही", "जी हाँ", "हा",
       "అవును", "సరే", "కరెక్ట్", "ఔను"]
NO = ["no", "nope", "wrong", "illa", "nahi",
      "nahin", "nhi", "nai", "na", "galat", "illai", "thappu", "ledu", "kaadu", "tappu",
      "இல்ல", "இல்லை", "தப்பு", "இல்லீங்க",
      "नहीं", "नही", "ना", "गलत",
      "కాదు", "లేదు", "తప్పు", "లేరు"]

DONT_KNOW = ["don't know", "dont know", "not sure", "no idea", "theriyala", "pata nahi",
             "pata nahin", "nahi pata", "maloom nahi", "malum nahi", "yaad nahi", "theriyadhu",
             "teliyadu", "teliyadhu", "gurthu ledu",
             "தெரியல", "தெரியாது", "தெரியலை", "ஞாபகம் இல்ல",
             "पता नहीं", "मालूम नहीं", "नहीं पता", "याद नहीं",
             "తెలియదు", "తెలీదు", "గుర్తు లేదు"]

WATER = {
    "ankle": ["ankle", "கணுக்கால்", "टखने", "टखना", "చీలమండ", "takhne", "takhna", "takhno", "kanukkal"],
    "knee": ["knee", "முட்டி", "முழங்கால்", "घुटने", "घुटना", "మోకాలి", "మోకాలు", "మోకాళ్ళ",
             "ghutne", "ghutna", "ghutno", "mutti", "muttu", "mokalu", "mokaali", "mokalla"],
    "waist": ["waist", "hip", "இடுப்பு", "कमर", "నడుము", "kamar", "iduppu", "idupu", "nadumu"],
    "chest": ["chest", "நெஞ்சு", "மார்பு", "छाती", "ఛాతీ", "chhati", "chati", "chaati", "nenju"],
    "neck": ["neck", "கழுத்து", "गर्दन", "గొంతు", "మెడ", "gardan", "kazhuthu", "meda"],
}

FLOORS = [  # checked in this order
    ("terrace", ["terrace", "roof", "மொட்டை மாடி", "மொட்டைமாடி", "छत", "టెర్రస్", "డాబా", "chhat", "mottai maadi"]),
    ("ground", ["ground", "தரை", "கீழ் வீடு", "ग्राउंड", "भूतल", "నేల", "గ్రౌండ్"]),
    ("1", ["first", "1st", "முதல்", "पहली", "पहले", "మొదటి", "ఫస్ట్", "pehli", "pahli", "pehle", "mudhal"]),
    ("2", ["second", "2nd", "இரண்டாவது", "ரெண்டாவது", "दूसरी", "दूसरे", "రెండో", "రెండవ", "doosri", "dusri", "doosre", "dusre"]),
    ("3", ["third", "3rd", "மூணாவது", "மூன்றாவது", "तीसरी", "तीसरे", "మూడో", "మూడవ", "teesri", "tisri", "teesre"]),
    ("4", ["fourth", "4th", "நாலாவது", "நான்காவது", "चौथी", "चौथे", "నాలుగో", "నాలుగవ"]),
]

VULNERABLE_WORDS = [  # infant before child: "छोटा बच्चा" contains "बच्चा"
    ("infant", ["baby", "infant", "newborn", "chhota baccha", "chota baccha", "chhota bachcha", "கைக்குழந்தை", "பச்சக்குழந்தை", "छोटा बच्चा", "शिशु", "नवजात",
                "చిన్న బిడ్డ", "పసి", "పసిపాప"]),
    ("elderly", ["elderly", "old", "grandmother", "grandfather", "grandma", "grandpa", "paati", "thatha",
                 "வயசானவங்க", "வயதானவர்", "பாட்டி", "தாத்தா", "बुज़ुर्ग", "बुजुर्ग", "बूढ़", "दादी", "दादा",
                 "नानी", "नाना", "dadi", "dada", "nani", "nana", "buzurg", "budhe", "budhi", "vayasanavanga", "వృద్ధ", "ముసలి", "అమ్మమ్మ", "నానమ్మ", "తాతయ్య", "తాత"]),
    ("child", ["child", "kid", "baccha", "bachcha", "bacche", "bachche", "bachi", "kuzhandhai", "kozhandhai",
               "pilla", "pilladu", "குழந்தை", "பசங்க", "பையன்", "பொண்ணு", "बच्चा", "बच्चे", "बच्ची",
               "పిల్ల", "పిల్లాడు", "పాప", "బాబు"]),
    ("pregnant", ["pregnant", "கர்ப்பிணி", "கர்ப்பமா", "गर्भवती", "प्रेग्नेंट", "గర్భిణీ", "ప్రెగ్నెంట్"]),
    ("sick", ["sick", "ill", "patient", "fever", "beemar", "bimar", "bukhar", "mareez", "உடம்பு சரியில்ல", "நோயாளி", "காய்ச்சல்", "बीमार", "मरीज़",
              "मरीज", "बुखार", "అనారోగ్య", "జబ్బు", "జ్వరం"]),
    ("disabled", ["disabled", "wheelchair", "bedridden", "மாற்றுத்திறனாளி", "நடக்க முடியாது", "படுக்கையில",
                  "विकलांग", "व्हीलचेयर", "बिस्तर पर", "వికలాంగ", "వీల్ చైర్", "మంచం మీద"]),
]

# words that mean the reply is more than a simple answer -> let the LLM handle it
COMPLEX_HINTS = ["but", "ஆனா", "लेकिन", "कि", "కానీ", "street", "தெரு", "गली", "వీధి", "?",
                 "lekin", "magar", "aana", "kaani", "gali", "theru", "veedhi"]


# "no one is hurt" style answers to the danger question
DANGER_NONE = ["koi nahi", "kisi ko nahi", "koi ghayal nahi", "nobody", "no one", "none",
               "कोई नहीं", "किसी को नहीं", "कोई घायल नहीं", "yaarukkum illa", "யாருக்கும் இல்ல", "evariki ledu",
               "ఎవరికీ లేదు"]

# words that may sit next to a plain yes/no at a read-back ("haan sahi hai", "nahi galat he")
ANSWER_FILLER = {"hai", "he", "है", "ji", "जी", "bilkul", "बिल्कुल", "sir", "madam", "ஆமாங்க", "சரிங்க", "అండి"}


def _has(t: str, w: str) -> bool:
    """Is word/phrase w in t? English-letter words must match whole words ("ill" is not in "illa",
    "meda" is not in "medavakkam"). Native-script words match inside a word, for suffixes."""
    if w.isascii() and w[:1].isalpha():
        return re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) is not None
    return w in t


def _only(t: str, words: list[str]) -> bool:
    """Every word in t is one of `words` (or filler): a pure yes or a pure no, nothing else."""
    allowed = {x for w in words for x in w.split()} | ANSWER_FILLER
    return all(x in allowed for x in t.split())


def _norm(text: str) -> str:
    return re.sub(r"[.,!।]+", " ", text.lower()).strip()


def _is_short(t: str) -> bool:
    return len(t.split()) <= MAX_WORDS and not any(_has(t, h) for h in COMPLEX_HINTS)


def _starts_with_any(t: str, words: list[str]) -> bool:
    return any(t == w or t.startswith(w + " ") for w in words)


def _number(t: str) -> Optional[int]:
    found = set()
    for d in re.findall(r"\d+", t):
        found.add(int(d))
    for w, n in NUMBER_WORDS.items():
        if re.search(rf"(^|\s){re.escape(w)}", t):
            found.add(n)
    return found.pop() if len(found) == 1 else None


def quick_parse(text: str, last_action_key: Optional[str]) -> Optional[Extraction]:
    """Return an Extraction if this short reply can be understood without the LLM, else None."""
    if not last_action_key:
        return None
    t = _norm(text)
    # a bare PIN code ("600042", "6 0 0 0 4 2") answering where they are
    if last_action_key in ("ask:area", "ask:street") and t and re.fullmatch(r"[\d\s\W]+", t, flags=re.UNICODE):
        pin = clean_pincode(t)
        if pin:
            return Extraction(pincode=pin)
    if not t or not _is_short(t):
        return None

    is_yes = _starts_with_any(t, YES)
    is_no = _starts_with_any(t, NO)

    # "I don't know" is a real answer to any question: note it and move on (no LLM call) - but only
    # when it is (nearly) the whole answer. "తెలియదు, నీళ్ళు ఎక్కువ ఉన్నాయి" ("don't know, lots of
    # water") carries a fact and a language: the LLM reads that one.
    if last_action_key.startswith("ask:"):
        for d in DONT_KNOW:
            if _has(t, d):
                # strip punctuation only: vowel signs (ా, ्) aren't \w but are part of the word
                rest = "".join(" " if unicodedata.category(c).startswith("P") else c
                               for c in t.replace(d, " ")).split()
                if len(rest) <= 1:          # "pata nahi", "తెలియదు సార్", "I don't know ji"
                    return Extraction(dont_know=True)
                break

    if last_action_key in ("readback",):
        # only a PURE yes / no skips the LLM: "haan, second floor" carries a correction
        if is_yes and not is_no and _only(t, YES):
            return Extraction(confirmation="yes")
        if is_no and _only(t, NO):
            return Extraction(confirmation="no")
        return None

    if last_action_key == "ask:people":
        extra = [w for w in t.split() if w not in PEOPLE_FILLER and w not in NUMBER_WORDS and not w.isdigit()]
        if extra:
            return None
        n = _number(t)
        if n and 0 < n < 100:
            return Extraction(people_count=n)
        return None

    if last_action_key == "ask:water":
        hits = [level for level, words in WATER.items() if any(_has(t, w) for w in words)]
        if len(hits) == 1:
            return Extraction(water_level=hits[0])
        if is_no and len(t.split()) == 1:   # "is the water above your knee?" -> no = up to knee
            return Extraction(water_level="knee")
        if is_yes and len(t.split()) == 1:
            return Extraction(water_level="waist")
        return None

    if last_action_key == "ask:vulnerable_who":
        found, rest = [], t
        for kind, words in VULNERABLE_WORDS:
            hits = [w for w in words if _has(rest, w)]
            if hits:
                found.append(kind)
                for w in hits:  # remove matched words so "छोटा बच्चा" isn't also counted as "child"
                    rest = rest.replace(w, " ")
        return Extraction(vulnerable=found) if found else None

    if last_action_key == "ask:floor":
        for floor, words in FLOORS:
            if any(_has(t, w) for w in words):
                return Extraction(floor=floor)
        if m := re.search(r"\b(\d+)\b", t):
            return Extraction(floor=m.group(1))
        return None

    if last_action_key == "ask:danger":
        if any(_has(t, w) for w in DANGER_NONE):
            return Extraction(injured=False)
        if is_no and len(t.split()) <= 2:
            return Extraction(injured=False)
        return None

    if last_action_key == "ask:vulnerable":
        if is_no and len(t.split()) <= 2:
            return Extraction()  # nobody vulnerable; slot counts as answered
        if is_yes and len(t.split()) <= 2:
            return Extraction(vulnerable=["unspecified"])
        return None

    return None