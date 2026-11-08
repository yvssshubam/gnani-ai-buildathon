"""LLM prompts. Kept short on purpose: every token here is sent on every LLM call."""
from __future__ import annotations

EXTRACT_SYSTEM = """Extract facts from ONE caller utterance on a flood rescue phone line (Hindi/English/Tamil/Telugu/mixed).
Return ONLY a JSON object. Omit keys you have no info for.
The caller's words come from speech recognition and can contain sound-alike mistakes. Read them as a flood
caller would mean them ("వీళ్ళు చాలా ఎక్కువ" next to flooding is most likely "నీళ్ళు", water). But only record a
fact you are confident of: a guessed injury, number or place stays out, so the agent asks. In ack, never repeat
words that look misheard or make no sense; mention something you clearly understood.
Keys:
locality, street, door_no, building, floor, landmark: ALWAYS English letters, even if the caller used another script
  ("Velachery","Nehru Street","1","second","terrace")
street_native, building_native, landmark_native: same names exactly as the caller said them, in their script
  These must be real NAMES. "our house", "my home", "here", "మా ఇల్లు", "हमारा घर", "எங்க வீடு" are not names: leave the field out.
pincode: the 6-digit PIN code as digits, ONLY if they say one ("six zero zero zero four two" -> "600042")
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
  stay_or_move (should we stay/go up/leave) | electricity (wires, current, shock) | animal (snake etc.) |
  rephrase (they ask what a word in our question means, or say they didn't understand it: "floor means what?") |
  go_ahead (they offer to tell or ask if they should explain: "shall I tell you?", "बताऊँ?", "చెప్పనా?", "சொல்லட்டுமா?") | other
reply: ONLY if what they said is not simply an answer: an offer ("shall I tell you?"), partial information
  ("I only know the pin code, is that ok?"), or something our question doesn't cover. One short spoken sentence,
  max 12 words, in the CALL LANGUAGE's own script, responding to exactly that, e.g. "అవును, పిన్ కోడ్ చెప్పండి." /
  "हाँ, पिन कोड बताइए।" / "Yes, tell me the pin code." Never a promise or a time. Omit for normal answers.
panic: high if crying, screaming, repeating, very broken speech, or they say they fear for their life
  ("I'm going to die", "मैं मरने वाला हूँ", "we will drown", "చచ్చిపోతాను"); else low
spoken_language: ALWAYS include. hi|en|ta|te: the language of the caller's WORDS, judged from the words, not the letters.
  Speech-to-text sometimes writes one language in another's script: "முஜே பச்சாவோ" / "ముజే బచావో" is "mujhe bachao" -> hi.
  A few English words inside a Hindi/Tamil/Telugu sentence don't make it en.
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
PHRASE_SYSTEM = """You are the calm, kind voice of a flood rescue phone line.
Write ONE short spoken reply in simple, everyday spoken {lang_name}{script_note}.
At most 2 short sentences. Start with an acknowledgement of at most 4 words; never repeat the caller's words.
Then do ONLY this: {instruction}
Never promise when rescue will arrive. Output only the reply text."""

GREETING = {
    # Pre-recorded in voice mode. Hindi and English, and an invitation to speak in any language:
    # the caller's first sentence sets the call's language.
    "text": "बाढ़ बचाव हेल्पलाइन। बताइए, क्या हुआ है? Flood rescue line. Tell me what's happening, in any language.",
    "lang": "hi-IN",
}