"""Fixed things the agent says, in each language. No LLM needed.

Why fixed lines instead of LLM wording:
  - fewer API calls and tokens (free-tier limits)
  - faster (and in voice mode these can be pre-recorded)
  - every sentence on an emergency line is reviewed by a human

>>> REVIEW THE TAMIL, HINDI AND TELUGU LINES before the demo. Fix anything that sounds unnatural. <<<
"""
from __future__ import annotations

from typing import Optional

from .gazetteer import native_name

PHRASES: dict[str, dict[str, str]] = {
    "en-IN": {
        "ack": "Okay.",
        "calm": "I am here with you. Take a breath, we will do this together.",
        "ans_when_help": "I can't give an exact time, but your request is going to the rescue teams right now.",
        "ans_stay_or_move": "Stay where you are. If it is safe, go to the highest floor or terrace. Do not walk into the water.",
        "ans_electricity": "Stay away from wires and switches. Do not touch anything electrical near the water.",
        "ans_animal": "Move away from it slowly and stay on higher ground. Tell the rescue team when they come.",
        "handoff": "I am connecting you to a rescue officer now. Your ticket number is {digits}. Please stay on the line.",
        "danger1": "Is anyone hurt, or is the water rising fast right now?",
        "danger2": "Is anyone hurt? Yes or no.",
        "area1": "Where are you? Tell me the area and the street name.",
        "area2": "Just tell me the area name, or any big temple, school or bus stop near you.",
        "street1": "Which street, and what is the house number or building name? Which floor are you on?",
        "street2": "Is there any big temple, school, church or shop near your house?",
        "floor1": "Which floor are you on?",
        "people1": "How many people are with you, including you?",
        "people2": "Just tell me the number of people.",
        "vulnerable1": "Is anyone elderly, a small child or baby, pregnant, sick or disabled?",
        "vulnerable2": "Is there any old person, child or sick person with you? Yes or no.",
        "vulnerable_who1": "Who is it: an elderly person, a child or baby, a pregnant woman, or someone sick?",
        "water1": "How high is the water where you are: ankle, knee, waist or chest?",
        "water2": "Is the water above your knee? Yes or no.",
        "readback": "Let me check: {details}. Is that correct?",
        "ask_correction": "What is wrong? Tell me and I will fix it.",
        "close": "Your rescue request is registered, ticket number {digits}. Stay at the highest safe place, do not walk into the water, and save your phone battery. We will call you back.",
        "close_callback": "Your request is registered, ticket number {digits}. A rescue officer will call you back to confirm where you are. Keep the phone with you and save battery.",
        "urgent": "Your case is marked most urgent and a rescue officer is being alerted now.",
        # read-back pieces
        "people": "{n} people", "person": "1 person", "including": "including {list}",
        "at": "at {address}", "near": "near {landmark}", "door": "door number {x}",
        "floor_n": "{n} floor", "ground": "ground floor", "terrace": "terrace",
        "none": "no details yet", "sep": ", ",
    },
    "ta-IN": {
        "ack": "சரி.",
        "calm": "நான் உங்க கூடவே இருக்கேன். கொஞ்சம் மூச்சு விடுங்க, சேர்ந்து பார்த்துக்கலாம்.",
        "ans_when_help": "சரியான நேரம் சொல்ல முடியாது, ஆனா உங்க கோரிக்கை இப்பவே மீட்பு குழுவுக்கு போயிட்டு இருக்கு.",
        "ans_stay_or_move": "இருக்கற இடத்துலயே இருங்க. பாதுகாப்பா இருந்தா மேல் மாடிக்கோ மொட்டை மாடிக்கோ போங்க. தண்ணீர்ல நடக்காதீங்க.",
        "ans_electricity": "வயர், சுவிட்ச் பக்கம் போகாதீங்க. தண்ணீர் பக்கத்துல எந்த மின்சார பொருளையும் தொடாதீங்க.",
        "ans_animal": "மெதுவா அதுகிட்ட இருந்து விலகி, உயரமான இடத்துல இருங்க. மீட்பு குழு வந்தா சொல்லுங்க.",
        "handoff": "உங்களை இப்பவே ஒரு மீட்பு அதிகாரிகிட்ட இணைக்கிறேன். உங்க டிக்கெட் நம்பர் {digits}. லைன்லயே இருங்க.",
        "danger1": "யாருக்காவது அடிபட்டிருக்கா? இல்ல தண்ணீர் வேகமா ஏறுதா?",
        "danger2": "யாருக்காவது அடிபட்டிருக்கா? ஆமா இல்லன்னு சொல்லுங்க.",
        "area1": "நீங்க எங்க இருக்கீங்க? ஏரியா பேரும் தெரு பேரும் சொல்லுங்க.",
        "area2": "ஏரியா பேர் மட்டும் சொல்லுங்க, இல்ல பக்கத்துல ஏதாவது பெரிய கோவில், ஸ்கூல், பஸ் ஸ்டாப்?",
        "street1": "எந்த தெரு, வீட்டு நம்பர் இல்ல அபார்ட்மெண்ட் பேர் என்ன? எந்த மாடியில இருக்கீங்க?",
        "street2": "வீட்டு பக்கத்துல ஏதாவது பெரிய கோவில், ஸ்கூல், சர்ச் இல்ல கடை இருக்கா?",
        "floor1": "எந்த மாடியில இருக்கீங்க?",
        "people1": "உங்களையும் சேர்த்து எத்தனை பேர் இருக்கீங்க?",
        "people2": "எத்தனை பேர்னு நம்பர் மட்டும் சொல்லுங்க.",
        "vulnerable1": "கூட வயசானவங்க, சின்ன குழந்தை, கர்ப்பிணி, உடம்பு சரியில்லாதவங்க யாராவது இருக்காங்களா?",
        "vulnerable2": "வயசானவங்க இல்ல குழந்தை யாராவது இருக்காங்களா? ஆமா இல்லன்னு சொல்லுங்க.",
        "vulnerable_who1": "யாரு? வயசானவங்களா, குழந்தையா, கர்ப்பிணியா, இல்ல உடம்பு சரியில்லாதவங்களா?",
        "water1": "தண்ணீர் எவ்வளவு உயரம் இருக்கு? கணுக்கால், முட்டி, இடுப்பு, இல்ல நெஞ்சு அளவா?",
        "water2": "தண்ணீர் முட்டிக்கு மேல இருக்கா? ஆமா இல்லன்னு சொல்லுங்க.",
        "readback": "சரிபார்க்கிறேன்: {details}. சரியா?",
        "ask_correction": "எது தப்பா இருக்கு? சொல்லுங்க, சரி பண்றேன்.",
        "close": "உங்க மீட்பு கோரிக்கை பதிவாயிடுச்சு. டிக்கெட் நம்பர் {digits}. உயரமான பாதுகாப்பான இடத்துலயே இருங்க, தண்ணீர்ல நடக்காதீங்க, போன் பேட்டரியை சேமிங்க. நாங்க திரும்ப கூப்பிடுவோம்.",
        "close_callback": "உங்க கோரிக்கை பதிவாயிடுச்சு. டிக்கெட் நம்பர் {digits}. நீங்க இருக்கற இடத்தை உறுதி செய்ய ஒரு மீட்பு அதிகாரி திரும்ப கூப்பிடுவாங்க. போனை கையிலயே வெச்சுக்கோங்க, பேட்டரியை சேமிங்க.",
        "urgent": "உங்க நிலைமை மிக அவசரம்னு குறிச்சிருக்கோம், மீட்பு அதிகாரிக்கு இப்பவே தகவல் போயிடுச்சு.",
        "people": "{n} பேர்", "person": "1 பேர்", "including": "{list} உட்பட",
        "at": "{address}", "near": "{landmark} பக்கத்துல", "door": "கதவு எண் {x}",
        "floor_n": "{n}வது மாடி", "ground": "தரை தளம்", "terrace": "மொட்டை மாடி",
        "none": "இன்னும் விவரம் இல்ல", "sep": ", ",
    },
    "hi-IN": {
        "ack": "ठीक है।",
        "calm": "मैं आपके साथ हूँ। एक गहरी साँस लीजिए, हम मिलकर संभाल लेंगे।",
        "ans_when_help": "सही समय नहीं बता सकते, लेकिन आपकी रिक्वेस्ट अभी बचाव टीम को भेजी जा रही है।",
        "ans_stay_or_move": "जहाँ हैं वहीं रहिए। सुरक्षित हो तो सबसे ऊपर की मंज़िल या छत पर जाइए। पानी में मत चलिए।",
        "ans_electricity": "तारों और स्विच से दूर रहिए। पानी के पास किसी भी बिजली की चीज़ को मत छुइए।",
        "ans_animal": "धीरे से उससे दूर हटिए और ऊँची जगह पर रहिए। बचाव टीम आए तो उन्हें बताइए।",
        "handoff": "आपको अभी एक बचाव अधिकारी से जोड़ा जा रहा है। आपका टिकट नंबर {digits} है। लाइन पर बने रहिए।",
        "danger1": "क्या किसी को चोट लगी है, या पानी तेज़ी से बढ़ रहा है?",
        "danger2": "क्या किसी को चोट लगी है? हाँ या ना बताइए।",
        "area1": "आप कहाँ हैं? इलाके का नाम और गली का नाम बताइए।",
        "area2": "बस इलाके का नाम बताइए, या पास का कोई बड़ा मंदिर, स्कूल या बस स्टॉप।",
        "street1": "कौन सी गली, और मकान नंबर या बिल्डिंग का नाम क्या है? आप किस मंज़िल पर हैं?",
        "street2": "घर के पास कोई बड़ा मंदिर, स्कूल, चर्च या दुकान है?",
        "floor1": "आप किस मंज़िल पर हैं?",
        "people1": "आपको मिलाकर वहाँ कितने लोग हैं?",
        "people2": "बस लोगों की गिनती बताइए।",
        "vulnerable1": "क्या साथ में कोई बुज़ुर्ग, छोटा बच्चा, गर्भवती महिला, बीमार या विकलांग व्यक्ति है?",
        "vulnerable2": "क्या कोई बुज़ुर्ग या बच्चा साथ है? हाँ या ना।",
        "vulnerable_who1": "कौन है? बुज़ुर्ग, बच्चा, गर्भवती महिला, या कोई बीमार?",
        "water1": "पानी कितना ऊँचा है? टखने, घुटने, कमर या छाती तक?",
        "water2": "क्या पानी घुटने से ऊपर है? हाँ या ना।",
        "readback": "एक बार पक्का कर लूँ: {details}। क्या यह सही है?",
        "ask_correction": "क्या गलत है? बताइए, ठीक कर दिया जाएगा।",
        "close": "आपकी मदद की रिक्वेस्ट दर्ज हो गई है, टिकट नंबर {digits}। सबसे ऊँची सुरक्षित जगह पर रहिए, पानी में मत चलिए, और फ़ोन की बैटरी बचाइए। हम आपको वापस कॉल करेंगे।",
        "close_callback": "आपकी रिक्वेस्ट दर्ज हो गई है, टिकट नंबर {digits}। आपकी जगह पक्की करने के लिए एक बचाव अधिकारी आपको वापस कॉल करेगा। फ़ोन पास रखिए और बैटरी बचाइए।",
        "urgent": "आपका मामला सबसे ज़रूरी माना गया है, बचाव अधिकारी को अभी सूचना दी जा रही है।",
        "people": "{n} लोग", "person": "1 व्यक्ति", "including": "{list} समेत",
        "at": "{address}", "near": "{landmark} के पास", "door": "मकान नंबर {x}",
        "floor_n": "{n} मंज़िल", "ground": "ग्राउंड फ़्लोर", "terrace": "छत",
        "none": "अभी कोई जानकारी नहीं", "sep": ", ",
    },
    "te-IN": {
        "ack": "సరే.",
        "calm": "నేను మీతోనే ఉన్నాను. ఒక్కసారి ఊపిరి తీసుకోండి, కలిసి చూసుకుందాం.",
        "ans_when_help": "సరైన సమయం చెప్పలేను, కానీ మీ అభ్యర్థన ఇప్పుడే రెస్క్యూ టీమ్‌కు వెళ్తోంది.",
        "ans_stay_or_move": "ఉన్న చోటే ఉండండి. సురక్షితంగా ఉంటే పై అంతస్తుకు లేదా టెర్రస్‌కు వెళ్ళండి. నీళ్ళలో నడవకండి.",
        "ans_electricity": "వైర్లు, స్విచ్‌లకు దూరంగా ఉండండి. నీళ్ళ దగ్గర ఏ కరెంట్ వస్తువునూ ముట్టుకోకండి.",
        "ans_animal": "నెమ్మదిగా దాని నుంచి దూరంగా జరిగి, ఎత్తైన చోట ఉండండి. రెస్క్యూ టీమ్ వచ్చినప్పుడు చెప్పండి.",
        "handoff": "మిమ్మల్ని ఇప్పుడే ఒక రెస్క్యూ అధికారితో కలుపుతున్నాను. మీ టికెట్ నంబర్ {digits}. లైన్‌లోనే ఉండండి.",
        "danger1": "ఎవరికైనా దెబ్బ తగిలిందా? లేదా నీళ్ళు వేగంగా పెరుగుతున్నాయా?",
        "danger2": "ఎవరికైనా దెబ్బ తగిలిందా? అవును లేదా కాదు చెప్పండి.",
        "area1": "మీరు ఎక్కడ ఉన్నారు? ఏరియా పేరు, వీధి పేరు చెప్పండి.",
        "area2": "ఏరియా పేరు మాత్రం చెప్పండి, లేదా దగ్గర్లో ఏదైనా పెద్ద గుడి, స్కూల్, బస్ స్టాప్?",
        "street1": "ఏ వీధి, ఇంటి నంబర్ లేదా బిల్డింగ్ పేరు ఏంటి? మీరు ఏ అంతస్తులో ఉన్నారు?",
        "street2": "మీ ఇంటి దగ్గర ఏదైనా పెద్ద గుడి, స్కూల్, చర్చి లేదా షాప్ ఉందా?",
        "floor1": "మీరు ఏ అంతస్తులో ఉన్నారు?",
        "people1": "మీతో కలిపి ఎంత మంది ఉన్నారు?",
        "people2": "ఎంత మంది అని నంబర్ మాత్రమే చెప్పండి.",
        "vulnerable1": "మీతో వృద్ధులు, చిన్న పిల్లలు, గర్భిణీ, అనారోగ్యంగా ఉన్నవాళ్ళు లేదా వికలాంగులు ఎవరైనా ఉన్నారా?",
        "vulnerable2": "వృద్ధులు లేదా పిల్లలు ఎవరైనా ఉన్నారా? అవును లేదా కాదు.",
        "vulnerable_who1": "ఎవరు? వృద్ధులా, పిల్లలా, గర్భిణీనా, లేక అనారోగ్యంగా ఉన్నవారా?",
        "water1": "నీళ్ళు ఎంత ఎత్తు వరకు ఉన్నాయి? చీలమండ, మోకాలు, నడుము లేదా ఛాతీ వరకా?",
        "water2": "నీళ్ళు మోకాలి పైకి ఉన్నాయా? అవును లేదా కాదు.",
        "readback": "ఒకసారి సరిచూసుకుంటాను: {details}. ఇది సరైనదేనా?",
        "ask_correction": "ఏది తప్పు? చెప్పండి, సరిచేస్తాను.",
        "close": "మీ రెస్క్యూ అభ్యర్థన నమోదైంది, టికెట్ నంబర్ {digits}. ఎత్తైన సురక్షితమైన చోటే ఉండండి, నీళ్ళలో నడవకండి, ఫోన్ బ్యాటరీ ఆదా చేయండి. మేము మళ్ళీ కాల్ చేస్తాము.",
        "close_callback": "మీ అభ్యర్థన నమోదైంది, టికెట్ నంబర్ {digits}. మీరు ఎక్కడ ఉన్నారో నిర్ధారించడానికి ఒక రెస్క్యూ అధికారి మళ్ళీ కాల్ చేస్తారు. ఫోన్ దగ్గరే ఉంచుకోండి, బ్యాటరీ ఆదా చేయండి.",
        "urgent": "మీ పరిస్థితిని అత్యంత అత్యవసరంగా గుర్తించాము, రెస్క్యూ అధికారికి ఇప్పుడే సమాచారం పంపుతున్నాము.",
        "people": "{n} మంది", "person": "1 వ్యక్తి", "including": "{list} తో సహా",
        "at": "{address}", "near": "{landmark} దగ్గర", "door": "ఇంటి నంబర్ {x}",
        "floor_n": "{n}వ అంతస్తు", "ground": "గ్రౌండ్ ఫ్లోర్", "terrace": "టెర్రస్",
        "none": "ఇంకా వివరాలు లేవు", "sep": ", ",
    },
}

VULNERABLE_WORDS = {
    "en-IN": {"elderly": "elderly", "child": "child", "infant": "baby", "pregnant": "pregnant woman",
              "disabled": "disabled person", "sick": "sick person", "unspecified": "someone vulnerable"},
    "ta-IN": {"elderly": "வயசானவங்க", "child": "குழந்தைங்க", "infant": "கைக்குழந்தை", "pregnant": "கர்ப்பிணி",
              "disabled": "மாற்றுத்திறனாளி", "sick": "உடம்பு சரியில்லாதவங்க", "unspecified": "உதவி தேவைப்படுறவங்க"},
    "hi-IN": {"elderly": "बुज़ुर्ग", "child": "बच्चे", "infant": "छोटा बच्चा", "pregnant": "गर्भवती महिला",
              "disabled": "विकलांग व्यक्ति", "sick": "बीमार व्यक्ति", "unspecified": "कमज़ोर व्यक्ति"},
    "te-IN": {"elderly": "వృద్ధులు", "child": "పిల్లలు", "infant": "చిన్న బిడ్డ", "pregnant": "గర్భిణీ",
              "disabled": "వికలాంగులు", "sick": "అనారోగ్యంతో ఉన్నవారు", "unspecified": "సహాయం అవసరమైనవారు"},
}

ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
                 "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
ORDINALS = {
    "en-IN": {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"},
    "ta-IN": {1: "முதல் மாடி", 2: "இரண்டாவது மாடி", 3: "மூணாவது மாடி", 4: "நாலாவது மாடி", 5: "அஞ்சாவது மாடி"},
    "hi-IN": {1: "पहली मंज़िल", 2: "दूसरी मंज़िल", 3: "तीसरी मंज़िल", 4: "चौथी मंज़िल", 5: "पाँचवीं मंज़िल"},
    "te-IN": {1: "మొదటి అంతస్తు", 2: "రెండో అంతస్తు", 3: "మూడో అంతస్తు", 4: "నాలుగో అంతస్తు", 5: "ఐదో అంతస్తు"},
}


def _p(lang: str) -> dict[str, str]:
    return PHRASES.get(lang, PHRASES["en-IN"])


def say(key: str, lang: str, **kw) -> str:
    return _p(lang)[key].format(**kw)


def floor_number(floor: Optional[str]) -> Optional[int | str]:
    """'first' / '1' / '1st' -> 1; 'ground' -> 'ground'; 'terrace'/'roof' -> 'terrace'."""
    if not floor:
        return None
    f = floor.strip().lower()
    if f in ("ground", "g", "0", "ground floor"):
        return "ground"
    if f in ("terrace", "roof", "rooftop"):
        return "terrace"
    if f in ORDINAL_WORDS:
        return ORDINAL_WORDS[f]
    digits = "".join(ch for ch in f if ch.isdigit())
    return int(digits) if digits else None


def floor_text(floor: Optional[str], lang: str) -> Optional[str]:
    n = floor_number(floor)
    if n is None:
        return None
    p = _p(lang)
    if n == "ground":
        return p["ground"]
    if n == "terrace":
        return p["terrace"]
    if lang == "en-IN":
        return p["floor_n"].format(n=ORDINALS["en-IN"].get(n, f"{n}th"))
    return ORDINALS.get(lang, {}).get(n) or p["floor_n"].format(n=n)


def readback_details(t, lang: str) -> str:
    """Build the read-back sentence from the ticket, in the caller's language."""
    p = _p(lang)
    loc = t.location
    native = lang != "en-IN"
    bits = []
    if t.people_count:
        bits.append(p["person"] if t.people_count == 1 else p["people"].format(n=t.people_count))
    if t.vulnerable:
        words = VULNERABLE_WORDS.get(lang, VULNERABLE_WORDS["en-IN"])
        bits.append(p["including"].format(list=p["sep"].join(words.get(v, v) for v in t.vulnerable)))
    addr = [
        p["door"].format(x=loc.door_no) if loc.door_no else None,
        (loc.building_native if native and loc.building_native else loc.building),
        (loc.street_native if native and loc.street_native else loc.street),
        native_name(loc.locality, lang),
        floor_text(loc.floor, lang),
    ]
    addr_text = p["sep"].join(a for a in addr if a)
    if addr_text:
        bits.append(p["at"].format(address=addr_text))
    landmark = loc.landmark_native if native and loc.landmark_native else loc.landmark
    if landmark:
        bits.append(p["near"].format(landmark=landmark))
    return p["sep"].join(bits) or p["none"]