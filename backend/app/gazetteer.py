"""Chennai localities: turn spoken place names into map coordinates.

Coordinates are APPROXIMATE locality centres for the demo. Check them on a map
(and add more localities) before the final recording.

Each locality has English spellings and its Tamil name, because a Tamil caller's
transcript will say "வேளச்சேரி", not "Velachery".
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

from rapidfuzz import fuzz

from .models import LocConfidence, Location

LOCALITIES: list[dict] = [
    {"name": "Velachery", "aliases": ["velachery", "velacheri", "வேளச்சேரி"], "lat": 12.9815, "lon": 80.2180},
    {"name": "Tambaram", "aliases": ["tambaram", "thambaram", "தாம்பரம்"], "lat": 12.9249, "lon": 80.1000},
    {"name": "Mudichur", "aliases": ["mudichur", "mudichoor", "முடிச்சூர்"], "lat": 12.9180, "lon": 80.0730},
    {"name": "Varadharajapuram", "aliases": ["varadharajapuram", "varadarajapuram", "வரதராஜபுரம்"], "lat": 12.9170, "lon": 80.0670},
    {"name": "Pallikaranai", "aliases": ["pallikaranai", "pallikarani", "பள்ளிக்கரணை"], "lat": 12.9349, "lon": 80.2137},
    {"name": "Madipakkam", "aliases": ["madipakkam", "மடிப்பாக்கம்"], "lat": 12.9647, "lon": 80.1961},
    {"name": "Perungudi", "aliases": ["perungudi", "பெருங்குடி"], "lat": 12.9653, "lon": 80.2461},
    {"name": "Sholinganallur", "aliases": ["sholinganallur", "sholinganalur", "சோழிங்கநல்லூர்"], "lat": 12.9010, "lon": 80.2279},
    {"name": "Medavakkam", "aliases": ["medavakkam", "மேடவாக்கம்"], "lat": 12.9200, "lon": 80.1920},
    {"name": "Perumbakkam", "aliases": ["perumbakkam", "பெரும்பாக்கம்"], "lat": 12.9050, "lon": 80.1980},
    {"name": "Semmancheri", "aliases": ["semmancheri", "செம்மஞ்சேரி"], "lat": 12.8680, "lon": 80.2270},
    {"name": "Adyar", "aliases": ["adyar", "adayar", "அடையாறு", "அடையார்"], "lat": 13.0012, "lon": 80.2565},
    {"name": "Kotturpuram", "aliases": ["kotturpuram", "கோட்டூர்புரம்"], "lat": 13.0186, "lon": 80.2406},
    {"name": "Saidapet", "aliases": ["saidapet", "சைதாப்பேட்டை"], "lat": 13.0213, "lon": 80.2231},
    {"name": "T. Nagar", "aliases": ["t nagar", "t. nagar", "thyagaraya nagar", "தி. நகர்", "தியாகராய நகர்", "टी नगर", "टी. नगर", "టీ నగర్", "టి నగర్"], "lat": 13.0418, "lon": 80.2341},
    {"name": "K.K. Nagar", "aliases": ["kk nagar", "k.k. nagar", "k k nagar", "கே.கே. நகர்", "கே.கே.நகர்", "के के नगर", "केके नगर", "के.के. नगर", "కేకే నగర్", "కె.కె. నగర్"], "lat": 13.0410, "lon": 80.1990},
    {"name": "Ashok Nagar", "aliases": ["ashok nagar", "அசோக் நகர்"], "lat": 13.0350, "lon": 80.2120},
    {"name": "Kodambakkam", "aliases": ["kodambakkam", "கோடம்பாக்கம்"], "lat": 13.0521, "lon": 80.2255},
    {"name": "Mylapore", "aliases": ["mylapore", "மயிலாப்பூர்"], "lat": 13.0339, "lon": 80.2619},
    {"name": "Anna Nagar", "aliases": ["anna nagar", "அண்ணா நகர்"], "lat": 13.0850, "lon": 80.2101},
    {"name": "Kolathur", "aliases": ["kolathur", "கொளத்தூர்"], "lat": 13.1240, "lon": 80.2120},
    {"name": "Vyasarpadi", "aliases": ["vyasarpadi", "viyasarpadi", "வியாசர்பாடி"], "lat": 13.1185, "lon": 80.2600},
    {"name": "Pulianthope", "aliases": ["pulianthope", "pulianthoppu", "புளியந்தோப்பு"], "lat": 13.0960, "lon": 80.2630},
    {"name": "Royapuram", "aliases": ["royapuram", "ராயபுரம்"], "lat": 13.1137, "lon": 80.2954},
    {"name": "Tiruvottiyur", "aliases": ["tiruvottiyur", "thiruvottiyur", "திருவொற்றியூர்"], "lat": 13.1643, "lon": 80.3001},
    {"name": "Manali", "aliases": ["manali", "மணலி"], "lat": 13.1667, "lon": 80.2667},
    {"name": "Ennore", "aliases": ["ennore", "ennur", "எண்ணூர்"], "lat": 13.2146, "lon": 80.3203},
    {"name": "Ambattur", "aliases": ["ambattur", "அம்பத்தூர்"], "lat": 13.1143, "lon": 80.1548},
    {"name": "Avadi", "aliases": ["avadi", "ஆவடி"], "lat": 13.1067, "lon": 80.0970},
    {"name": "Porur", "aliases": ["porur", "போரூர்"], "lat": 13.0382, "lon": 80.1565},
    {"name": "Chromepet", "aliases": ["chromepet", "chrompet", "krompet", "குரோம்பேட்டை"], "lat": 12.9516, "lon": 80.1462},
    {"name": "Pallavaram", "aliases": ["pallavaram", "பல்லாவரம்"], "lat": 12.9675, "lon": 80.1491},
]

_BY_NAME = {loc["name"].lower(): loc for loc in LOCALITIES}


# ---------------------------------------------------------------- street names in English letters
# Responders read the ticket in English. If the model only gave the caller's own-script street
# ("नेहरू स्ट्रीट", "காந்தி தெரு"), we convert it here: known words from this table first,
# anything else letter-by-letter. The original stays in street_native for the read-back.
PLACE_WORDS = {
    # street / road words
    "स्ट्रीट": "Street", "गली": "Street", "रोड": "Road", "मार्ग": "Road", "सड़क": "Road",
    "नगर": "Nagar", "कॉलोनी": "Colony", "मेन": "Main", "क्रॉस": "Cross", "लेन": "Lane",
    "தெரு": "Street", "சாலை": "Road", "ரோடு": "Road", "நகர்": "Nagar", "குறுக்கு": "Cross",
    "பிரதான": "Main", "மெயின்": "Main", "காலனி": "Colony", "தெருவு": "Street",
    "వీధి": "Street", "రోడ్డు": "Road", "రోడ్": "Road", "నగర్": "Nagar", "కాలనీ": "Colony",
    # common names (exact spellings responders expect)
    # English words in Devanagari (Hindi speakers use these in addresses)
    "लेक": "Lake", "व्यू": "View", "पार्क": "Park", "चर्च": "Church", "स्कूल": "School",
    "स्टेशन": "Station", "बस": "Bus", "स्टॉप": "Stop", "स्टैंड": "Stand", "मार्केट": "Market",
    "हॉस्पिटल": "Hospital", "अस्पताल": "Hospital", "टेम्पल": "Temple", "बिल्डिंग": "Building",
    "अपार्टमेंट": "Apartment", "अपार्टमेंट्स": "Apartments", "फ्लैट": "Flat", "ब्लॉक": "Block",
    "टावर": "Tower", "ब्रिज": "Bridge", "पुल": "Bridge", "पुलिस": "Police", "मॉल": "Mall",
    "फर्स्ट": "First", "सेकंड": "Second", "थर्ड": "Third", "मस्जिद": "Masjid",
    "नेहरू": "Nehru", "गांधी": "Gandhi", "गाँधी": "Gandhi", "अंबेडकर": "Ambedkar", "कामराज": "Kamaraj",
    "अन्ना": "Anna", "राजीव": "Rajiv", "इंदिरा": "Indira", "पेरियार": "Periyar", "मंदिर": "Temple",
    "காந்தி": "Gandhi", "நேரு": "Nehru", "அம்பேத்கர்": "Ambedkar", "காமராஜர்": "Kamarajar",
    "அண்ணா": "Anna", "பெரியார்": "Periyar", "ராஜீவ்": "Rajiv", "இந்திரா": "Indira",
    "பாரதி": "Bharathi", "भारती": "Bharathi", "கோவில்": "Kovil", "கோயில்": "Kovil", "முருகன்": "Murugan", "பிள்ளையார்": "Pillaiyar",
    "గాంధీ": "Gandhi", "నెహ్రూ": "Nehru", "అంబేద్కర్": "Ambedkar",
}

_SCRIPTS = [  # (first code point, last code point, sanscript scheme name)
    (0x0900, 0x097F, "devanagari"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"),
]


def _script_of(word: str) -> Optional[str]:
    for ch in word:
        for lo, hi, name in _SCRIPTS:
            if lo <= ord(ch) <= hi:
                return name
    return None


def _locality_word(word: str) -> Optional[str]:
    """A locality we already know in Tamil -> its English name. Handles suffixes (வேளச்சேரியில்)."""
    for loc in LOCALITIES:
        for alias in loc["aliases"]:
            if not alias.isascii() and " " not in alias and word.startswith(alias):
                return loc["name"]
    return None


_warned_missing_lib = False


def _letters(word: str, script: str) -> str:
    """Rough letter-by-letter conversion for a word not in PLACE_WORDS."""
    global _warned_missing_lib
    try:
        from indic_transliteration.sanscript import IAST, transliterate
    except ImportError:          # library missing: keep the word as said rather than crash a call
        if not _warned_missing_lib:
            _warned_missing_lib = True
            logging.getLogger("gazetteer").warning(
                "indic-transliteration is not installed: street names stay in the caller's script. "
                "Fix: python -m pip install indic-transliteration")
        return word
    if script == "devanagari":
        # the English "o" sound (स्टॉप, ऑटो) has no IAST letter; treat it as a plain "o"
        word = word.replace("ॉ", "ो").replace("ऑ", "ओ")
    out = transliterate(word, script, IAST)
    out = out.replace("ś", "sh").replace("ṣ", "sh")              # shiva, not siva
    if script in ("devanagari", "telugu"):
        out = re.sub(r"c(?!h)", "ch", out)                        # IAST "c" is the "ch" sound
    if script == "devanagari":
        out = out.replace("ph", "f")                              # फ in Hindi is usually "f"
    if script == "tamil":
        # Tamil script has no separate g/d/b letters; the library guesses the aspirated form
        out = out.replace("gh", "g").replace("dh", "d").replace("bh", "b").replace("ṉ", "n")
    # anusvara: "m" before p/b/m and at the end of a word (tambaram), otherwise "n" (gandhi)
    out = re.sub(r"ṃ(?=[pbm]|$)", "m", out).replace("ṃ", "n")
    # strip accents: ā -> a, ṭ -> t ...
    out = "".join(c for c in unicodedata.normalize("NFD", out) if unicodedata.category(c) != "Mn")
    # Hindi doesn't say the silent final "a" (नगर -> nagar, not nagara), but a written ा stays (चंद्रा)
    if script == "devanagari" and len(out) > 2 and out.endswith("a") and not word.endswith("ा"):
        out = out[:-1]
    return out.capitalize()


def to_english_letters(text: Optional[str]) -> Optional[str]:
    """'नेहरू स्ट्रीट' -> 'Nehru Street', 'காந்தி தெரு' -> 'Gandhi Street'. English text is returned as is."""
    if not text:
        return text
    words = []
    for word in text.split():
        script = _script_of(word)
        if script is None:
            words.append(word)
        elif word in PLACE_WORDS:
            words.append(PLACE_WORDS[word])
        elif _locality_word(word):
            words.append(_locality_word(word))
        else:
            words.append(_letters(word, script))
    return " ".join(words)


def is_english_letters(text: Optional[str]) -> bool:
    return bool(text) and _script_of(text) is None


def _norm(text: str) -> str:
    # Remove punctuation/symbols only. Don't use \w: it drops Tamil vowel signs and breaks words.
    cleaned = "".join(" " if unicodedata.category(ch)[0] in "PS" and ch != "." else ch for ch in text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def match_locality(text: Optional[str]) -> Optional[dict]:
    """Find the locality mentioned in `text` (English or Tamil). Returns the gazetteer entry or None."""
    if not text:
        return None
    t = _norm(text)
    if t in _BY_NAME:
        return _BY_NAME[t]
    # 1) exact alias inside the text. Tamil aliases match inside a longer word (suffixes like
    #    வேளச்சேரியில்); English-letter aliases only as whole words, so "t nagar" is not found
    #    inside "vasant nagar".
    for loc in LOCALITIES:
        for alias in loc["aliases"]:
            if (_whole_words(alias, t) if alias.isascii() else alias in t):
                return loc
    # Hindi/Telugu script ("वेलाचेरी में"): we only store English + Tamil names, so convert
    # to English letters first: वेलाचेरी -> velacheri.
    script = _script_of(t)
    if script in ("devanagari", "telugu"):
        t = " ".join(_letters(w, script).lower().replace("chch", "ch")
                     if _script_of(w) else w for w in t.split())
    # 2) fuzzy match for misspellings / STT slips ("velacheri", "pallikarnai"), word by word.
    #    Comparing whole strings let any "... Nagar" match "T. Nagar": the shared word "nagar"
    #    was most of the short name. Now every word of the name has to be there.
    words = [w for w in re.split(r"[\s.]+", t) if w]
    best, best_score = None, 0.0
    for loc in LOCALITIES:
        for alias in loc["aliases"]:
            if not alias.isascii():
                continue
            score = _fuzzy_words(alias, words)
            if score > best_score:
                best, best_score = loc, score
    return best if best_score >= 85 else None


def _whole_words(alias: str, text: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text) is not None


def _fuzzy_words(alias: str, words: list[str]) -> float:
    """How well `alias` matches some run of `words`, 0-100. Each word of the alias must match a word
    of the text, in order: short words (the "t" of "t nagar", "kk") exactly, longer ones allowing
    for a spelling slip. A one-word name may also be split in two by speech-to-text ("vela cheri")."""
    parts = [a for a in re.split(r"[\s.]+", alias) if a]
    if not parts:
        return 0.0
    best = 0.0
    for i in range(len(words) - len(parts) + 1):
        scores = []
        for a, w in zip(parts, words[i:i + len(parts)]):
            if len(a) <= 3:
                score = 100.0 if a == w else 0.0
            else:
                score = fuzz.ratio(a, w)
                if 0 < len(w) - len(a) <= 4:
                    # a short ending stuck to the name: "tambaramlo" (Telugu "in Tambaram")
                    score = max(score, fuzz.ratio(a, w[:len(a)]))
            if score < 80:
                break
            scores.append(score)
        else:
            best = max(best, sum(scores) / len(scores))
    if len(parts) == 1 and len(parts[0]) >= 7:
        for a, b in zip(words, words[1:]):
            best = max(best, fuzz.ratio(parts[0], a + b))
    return best


SCRIPT_CHECK = {"ta-IN": (0x0B80, 0x0BFF)}


def native_name(locality: Optional[str], lang: str) -> Optional[str]:
    """Locality name in the caller's script, if we have it (e.g. Velachery -> வேளச்சேரி)."""
    if not locality or lang not in SCRIPT_CHECK:
        return locality
    lo, hi = SCRIPT_CHECK[lang]
    loc = _BY_NAME.get(locality.lower())
    if loc:
        for alias in loc["aliases"]:
            if alias and lo <= ord(alias[0]) <= hi:
                return alias
    return locality


def clean_pincode(value) -> Optional[str]:
    """An Indian PIN code: 6 digits, not starting with 0. Digits in any script; spaces allowed."""
    if value is None:
        return None
    digits = "".join(str(unicodedata.digit(c)) for c in str(value) if unicodedata.digit(c, None) is not None)
    return digits if len(digits) == 6 and digits[0] != "0" else None


def resolve(location: Location) -> Location:
    """Fill coordinates and confidence from whatever parts of the address we have."""
    loc = match_locality(location.locality)
    if loc is None and (location.landmark or location.landmark_native):
        # the native text matches Tamil aliases; check it before English letters are made from it
        loc = match_locality(location.landmark_native) or match_locality(location.landmark)
    if loc:
        location.locality = loc["name"]
        location.lat, location.lon = loc["lat"], loc["lon"]

    # Responders read street/building in English letters. If the model only gave the caller's
    # own-script name (or put the native text in the English field), convert it here.
    if not is_english_letters(location.street) and (location.street or location.street_native):
        location.street = to_english_letters(location.street or location.street_native)
    if not is_english_letters(location.building) and (location.building or location.building_native):
        location.building = to_english_letters(location.building or location.building_native)
    if not is_english_letters(location.landmark) and (location.landmark or location.landmark_native):
        location.landmark = to_english_letters(location.landmark or location.landmark_native)

    has_locality = loc is not None or bool(location.pincode)   # a PIN code narrows it to an area
    has_street = bool(location.street)
    has_point = bool(location.door_no or location.building)

    if has_locality and has_street and has_point:
        location.confidence = LocConfidence.EXACT
    elif has_locality and (has_street or has_point):
        location.confidence = LocConfidence.STREET
    elif has_locality:
        location.confidence = LocConfidence.AREA
    else:
        location.confidence = LocConfidence.UNKNOWN
    return location