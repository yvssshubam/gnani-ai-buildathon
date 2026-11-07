"""LLM prompts. Kept short on purpose: every token here is sent on every LLM call."""
from __future__ import annotations

EXTRACT_SYSTEM = """Extract facts from ONE caller utterance on a Chennai flood rescue line (Tamil/English/Hindi/Telugu/mixed).
Return ONLY a JSON object. Omit keys you have no info for.
Keys:
locality, street, door_no, building, floor, landmark: ALWAYS English letters, even if the caller used another script
  ("Velachery","Nehru Street","1","second","terrace")
street_native, building_native, landmark_native: same names exactly as the caller said them, in their script
people_count: int, ONLY if a number is said (never count people yourself)
vulnerable: list of elderly|child|infant|pregnant|disabled|sick
medical_need: short English text
water_level: none|ankle|knee|waist|chest|neck|roof, ONLY if a height is said ("water came in" or "rising" is NOT a level)
water_rising, injured, structure_unsafe, trapped: true/false
medical_emergency: true only if life-threatening (unconscious, not breathing, heavy bleeding, chest pain, labour)
needs: list of rescue|food|water|medicine|info (water inside home / stuck / asking for help -> rescue)
confirmation: yes|no when answering a read-back
correction: true if changing earlier details (incl. giving new details instead of yes/no after a read-back)
asks_for_human: true if they want a real person
dont_know: true if they say they don't know / can't tell what was asked (e.g. the street name)
ack: ALWAYS include. Max 6 words, casual spoken style, in the CALL LANGUAGE given under Known,
  even if this utterance is in English ("Church Road, first floor" in a Hindi call -> "चर्च रोड, ठीक है").
  Use that language's OWN script, never English letters: "गलत है, समझ गया", not "galat, samjha".
  It MUST mention one specific thing they just said (a person, place or situation), not just "understood".
  Good: "பாட்டி கூட இருக்காங்க, புரிஞ்சுது" / "காந்தி தெரு, சரி" / "पानी बढ़ रहा है, समझ गया" / "నీళ్ళు పెరుగుతున్నాయి, అర్థమైంది"
  Bad: "புரிந்தது" (too generic). No question, no promise, never a time.
caller_question: if they asked or raised something: when_help (when will help/boat come) |
  stay_or_move (should we stay/go up/leave) | electricity (wires, current, shock) | animal (snake etc.) | other
panic: high if crying, screaming, repeating, very broken speech; else low
Use the last question for context ("no" after "is anyone hurt?" -> injured false).
A clear statement counts even if nothing was asked: "कोई घायल नहीं" / "nobody is hurt" -> injured false.
Not answering a question is NOT "no": if they talk about something else, leave that field out.
Common spellings: காந்தி->Gandhi, நேரு->Nehru, கோவில்->temple, नेहरू स्ट्रीट->Nehru Street, गांधी रोड->Gandhi Road, गली->Street. paati/thatha/grandmother->elderly, baby/kuzhandhai->infant."""


def extract_user_prompt(utterance: str, last_question: str | None, known_summary: str) -> str:
    return (
        f"Known: {known_summary or '-'}\n"
        f"Last question: {last_question or '-'}\n"
        f"Caller: {utterance}"
    )


# Only used if you switch reply wording back to the LLM (see llm.phrase). Not used by default.
PHRASE_SYSTEM = """You are the calm, kind voice of a flood rescue phone line in Chennai.
Write ONE short spoken reply in simple, everyday spoken {lang_name}{script_note}.
At most 2 short sentences. Start with an acknowledgement of at most 4 words; never repeat the caller's words.
Then do ONLY this: {instruction}
Never promise when rescue will arrive. Output only the reply text."""

GREETING = {
    # Pre-recorded in voice mode. Tamil first (Chennai), then English.
    "text": "வெள்ள மீட்பு உதவி மையம். என்ன நடக்கிறது என்று சொல்லுங்கள். Flood rescue line. Please tell me what is happening.",
    "lang": "ta-IN",
}