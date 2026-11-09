"""Caller intents caught by rule, with no LLM delay (design v2, sections 5.4 and 7.4).

Each list holds phrases in English, Hindi, Telugu and Tamil: in their own scripts and as typed
in English letters. Matching is a plain substring check on the lower-cased text.

The Telugu and Tamil phrases are drafts and need a native speaker's check.
"""
from __future__ import annotations

REQUEST_HUMAN = "request_human"   # "let me talk to a person"
REFUSE_AI = "refuse_ai"           # "I won't talk to a machine"
ASK_ROBOT = "ask_robot"           # "are you a robot?"
STATUS_QUERY = "status_query"     # "when will the boat come?", "any update?"
ANGER = "anger"                   # swearing or shouting at the agent: distress, not abuse

PATTERNS: dict[str, list[str]] = {
    REFUSE_AI: [
        "won't talk to a machine", "will not talk to a machine", "not talking to a machine",
        "don't want to talk to a machine", "don't want a machine", "won't talk to a robot",
        "मशीन से बात नहीं", "मशीन से नहीं", "रोबोट से बात नहीं",
        "machine se baat nahi", "machine se nahi", "robot se baat nahi",
        "మెషిన్‌తో మాట్లాడను", "మెషిన్ తో మాట్లాడను", "యంత్రంతో మాట్లాడను", "machine tho matladanu",
        "மெஷின்கிட்ட பேச மாட்டேன்", "மெஷின் கிட்ட பேச மாட்டேன்", "machine kitta pesa maatten",
    ],
    REQUEST_HUMAN: [
        "real person", "a human", "talk to someone", "talk to a person", "speak to someone",
        "speak to a person", "talk to an officer", "speak to an officer", "not a machine", "not a robot",
        "इंसान से बात", "आदमी से बात", "किसी से बात करा", "किसी से बात करनी", "अधिकारी से बात", "ऑफिसर से बात",
        "insaan se baat", "insan se baat", "aadmi se baat", "admi se baat", "kisi se baat kara",
        "kisi se baat karni", "officer se baat", "officer do",
        "మనిషితో మాట్లాడాలి", "మనిషి తో మాట్లాడాలి", "అధికారితో మాట్లాడాలి", "ఆఫీసర్‌తో మాట్లాడాలి",
        "ఆఫీసర్ ని ఇవ్వండి", "ఆఫీసర్‌ని ఇవ్వండి", "manishi tho matladali", "officer ni ivvandi",
        "ஆள்கிட்ட பேசணும்", "ஆள் கிட்ட பேசணும்", "அதிகாரிகிட்ட பேசணும்", "ஆபீசர்கிட்ட பேசணும்",
        "aal kitta pesanum", "officer kitta kudunga", "officer kitta pesanum",
    ],
    ASK_ROBOT: [
        "are you a robot", "are you a machine", "are you human", "are you a human", "is this a machine",
        "is this a robot", "is this a recording", "am i talking to a machine",
        "क्या आप मशीन", "क्या आप रोबोट", "आप मशीन हो", "आप रोबोट हो", "आप इंसान हो",
        "kya aap machine", "kya aap robot", "aap machine ho", "aap robot ho", "aap insaan ho",
        "మీరు రోబోటా", "మీరు మెషినా", "మీరు మనిషా", "meeru robota", "meeru machina",
        "நீங்க ரோபோவா", "நீங்க மெஷினா", "நீங்க மனுஷனா", "neenga robova", "neenga machina",
    ],
    STATUS_QUERY: [
        "any update", "what is the status", "what's the status", "status of", "when will the boat",
        "when will they come", "when will the team", "when will help come", "how long will",
        "कब आएगी", "कब आएँगे", "कब आएंगे", "कब तक आ", "कोई अपडेट", "स्टेटस",
        "kab aayegi", "kab ayegi", "kab aayenge", "kab ayenge", "kab tak aa", "koi update",
        "ఎప్పుడు వస్తారు", "ఎప్పుడు వస్తుంది", "ఏమైనా అప్‌డేట్", "eppudu vastaru", "eppudu vastundi",
        "எப்போ வருவாங்க", "எப்ப வருவாங்க", "எப்போ வரும்", "ஏதாவது அப்டேட்", "eppo varuvaanga", "eppa varuvanga",
    ],
    ANGER: [
        "are you deaf", "useless", "stupid", "shut up", "damn", "bloody",
        "बहरे हो", "बहरी हो", "बेवकूफ", "पागल हो", "बकवास", "bahre ho", "behre ho", "bewakoof", "pagal ho", "bakwas",
        "చెవిటి", "పిచ్చి", "వెధవ", "cheviti", "pichi", "vedhava",
        "செவிடா", "பைத்தியம்", "லூசு", "sevida", "loosu", "paithiyam",
    ],
}


def detect(text: str) -> set[str]:
    """All intents whose phrases appear in the text."""
    t = " ".join((text or "").lower().split())
    found = {intent for intent, phrases in PATTERNS.items() if any(p in t for p in phrases)}
    if REFUSE_AI in found:
        found.discard(REQUEST_HUMAN)   # refusing the machine already means "a human, please"
    return found