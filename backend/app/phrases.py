"""Fixed things the agent says, in each language. No LLM needed.

Why fixed lines instead of LLM wording:
  - fewer API calls and tokens (free-tier limits)
  - faster (and in voice mode these can be pre-recorded)
  - every sentence on an emergency line is reviewed by a human

>>> Write the way people talk on the phone, not the way a form is written: everyday words, and the
English words everyone already uses (floor, area, officer, phone, time). Hindi uses female verb
forms (the agent voice is female). The Tamil lines still need a Tamil speaker's check. <<<
"""
from __future__ import annotations

from typing import Optional

from .gazetteer import native_name

PHRASES: dict[str, dict[str, str]] = {
    "en-IN": {
        "ack": "Okay.",
        "not_heard": "Sorry, I could not hear you. Please say that again.",
        "calm": "I am here with you. Take a breath, we will do this together.",
        "ans_when_help": "I can't give an exact time, but your request is going to the rescue teams right now.",
        "ans_stay_or_move": "Stay where you are. If it is safe, go to the highest floor or terrace. Do not walk into the water.",
        "ans_electricity": "Stay away from wires and switches. Do not touch anything electrical near the water.",
        "ans_animal": "Move away from it slowly and stay on higher ground. Tell the rescue team when they come.",
        "handoff": "I am passing your call to an officer. You are in line, please stay on the phone. Your ticket number is {digits}.",
        "danger1": "Is anyone hurt, or is the water rising fast right now?",
        "danger2": "Is anyone hurt? Yes or no.",
        "area1": "Where are you? Tell me the area and the street name.",
        "area2": "Just tell me the area name, or any big temple, school or bus stop near you.",
        "area3": "Can you see a temple, school, water tank or tall building near you? Tell me its name.",
        "again": "Take your time.",
        "rephrase": "Let me ask that more simply.",
        "go_ahead": "Yes, please tell me.",
        "p0_wait": "Your ticket number is {digits}. An officer is being alerted now. Stay on the line.",
        "p1_wait": "Your ticket number is {digits}. An officer will speak to you. Stay on the line, or hang up to save battery: your place is kept and we will call this number.",
        "still_in_line": "You are still in line for an officer. Stay on the phone.",
        "request_human_ack": "You are in line for an officer. While you wait, one question.",
        "anger_ack": "I hear you. I am passing this on to get you help.",
        "yes_automated": "Yes, I am an automated assistant. You are still in line for an officer.",
        "status_deflect": "I can't give updates or a time on this line. Your request is registered.",
        "new_info": "Do you have any new information?",
        "noted": "Noted.",
        "one_person": "Please give the phone to one person, and hold it close to your mouth.",
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
        "close": "Your rescue request is registered, ticket number {digits}. An officer will review it, and a team will be sent. Stay at the highest safe place, do not walk into the water, and save your phone battery.",
        "close_callback": "Your request is registered, ticket number {digits}. A rescue officer will call you back to confirm where you are. Keep the phone with you and save battery.",
        "urgent": "Your case is marked most urgent and a rescue officer is being alerted now.",
        # read-back pieces
        "people": "{n} people", "person": "1 person", "including": "including {list}",
        "at": "at {address}", "near": "near {landmark}", "door": "door number {x}",
        "floor_n": "{n} floor", "ground": "ground floor", "terrace": "terrace", "pin": "pin code {x}",
        "none": "no details yet", "sep": ", ",
    },
    "ta-IN": {
        "ack": "சரி.",
        "not_heard": "சாரி, சரியா கேக்கல. இன்னொரு தடவை சொல்லுங்க.",
        "calm": "நான் உங்க கூடவே இருக்கேன். கொஞ்சம் மூச்சு விடுங்க, சேர்ந்து பார்த்துக்கலாம்.",
        "ans_when_help": "டைம் சரியா சொல்ல முடியாது, ஆனா உங்க விஷயம் இப்பவே டீமுக்கு போயிட்டு இருக்கு.",
        "ans_stay_or_move": "இருக்கற இடத்துலயே இருங்க. பாதுகாப்பா இருந்தா மேல் மாடிக்கோ மொட்டை மாடிக்கோ போங்க. தண்ணீர்ல நடக்காதீங்க.",
        "ans_electricity": "வயர், சுவிட்ச் பக்கம் போகாதீங்க. தண்ணீர் பக்கத்துல எந்த மின்சார பொருளையும் தொடாதீங்க.",
        "ans_animal": "மெதுவா அதுகிட்ட இருந்து விலகி, உயரமான இடத்துல இருங்க. டீம் வந்தா சொல்லுங்க.",
        "handoff": "உங்க காலை ஒரு ஆபீசர்கிட்ட கொடுக்கறேன். நீங்க லைன்ல இருக்கீங்க, போனை வெக்காதீங்க. உங்க டிக்கெட் நம்பர் {digits}.",
        "danger1": "யாருக்காவது அடிபட்டிருக்கா? இல்ல தண்ணீர் வேகமா ஏறுதா?",
        "danger2": "யாருக்காவது அடிபட்டிருக்கா? ஆமா இல்லன்னு சொல்லுங்க.",
        "area1": "நீங்க எங்க இருக்கீங்க? ஏரியா பேரும் தெரு பேரும் சொல்லுங்க.",
        "area2": "ஏரியா பேர் மட்டும் சொல்லுங்க, இல்ல பக்கத்துல ஏதாவது பெரிய கோவில், ஸ்கூல், பஸ் ஸ்டாப்?",
        "area3": "பக்கத்துல ஏதாவது கோவில், ஸ்கூல், தண்ணீர் தொட்டி இல்ல பெரிய கட்டடம் தெரியுதா? அதோட பேர் சொல்லுங்க.",
        "again": "நிதானமா சொல்லுங்க.",
        "rephrase": "சுலபமா மறுபடியும் கேக்கறேன்.",
        "go_ahead": "சரி, சொல்லுங்க.",
        "p0_wait": "உங்க டிக்கெட் நம்பர் {digits}. இப்பவே ஆபீசர்கிட்ட சொல்றேன். போனை வெக்காதீங்க.",
        "p1_wait": "உங்க டிக்கெட் நம்பர் {digits}. ஒரு ஆபீசர் உங்ககிட்ட பேசுவாங்க. லைன்லயே இருங்க, இல்ல பேட்டரிக்காக போனை வெச்சிடுங்க: உங்க டர்ன் போகாது, இதே நம்பருக்கு கூப்பிடுவோம்.",
        "still_in_line": "நீங்க இன்னும் ஆபீசருக்காக லைன்லதான் இருக்கீங்க. போனை வெக்காதீங்க.",
        "request_human_ack": "நீங்க ஆபீசருக்காக லைன்ல இருக்கீங்க. அதுவரை ஒரு கேள்வி.",
        "anger_ack": "நான் கேக்கறேன். உங்களுக்கு உதவி கிடைக்க இதை அனுப்பறேன்.",
        "yes_automated": "ஆமா, நான் ஒரு ஆட்டோமேட்டிக் அசிஸ்டன்ட். நீங்க ஆபீசருக்காக லைன்லதான் இருக்கீங்க.",
        "status_deflect": "இந்த லைன்ல அப்டேட்டோ டைமோ சொல்ல முடியாது. உங்க விஷயத்தை எழுதிட்டோம்.",
        "new_info": "ஏதாவது புது விஷயம் தெரிஞ்சுதா?",
        "noted": "குறிச்சுக்கிட்டேன்.",
        "one_person": "போனை ஒருத்தர்கிட்ட மட்டும் கொடுங்க, வாய்க்கு பக்கத்துல வெச்சு பேசுங்க.",
        "street1": "எந்த தெரு, வீட்டு நம்பர் இல்ல அபார்ட்மெண்ட் பேர் என்ன? எந்த மாடியில இருக்கீங்க?",
        "street2": "வீட்டு பக்கத்துல ஏதாவது பெரிய கோவில், ஸ்கூல், சர்ச் இல்ல கடை இருக்கா?",
        "floor1": "எந்த மாடியில இருக்கீங்க?",
        "people1": "உங்களையும் சேர்த்து எத்தனை பேர் இருக்கீங்க?",
        "people2": "எத்தனை பேர்னு நம்பர் மட்டும் சொல்லுங்க.",
        "vulnerable1": "கூட வயசானவங்க, சின்ன குழந்தை, கர்ப்பிணி, உடம்பு சரியில்லாதவங்க, இல்ல நடக்க முடியாதவங்க யாராவது இருக்காங்களா?",
        "vulnerable2": "வயசானவங்க இல்ல குழந்தை யாராவது இருக்காங்களா? ஆமா இல்லன்னு சொல்லுங்க.",
        "vulnerable_who1": "யாரு? வயசானவங்களா, குழந்தையா, கர்ப்பிணியா, இல்ல உடம்பு சரியில்லாதவங்களா?",
        "water1": "தண்ணீர் எவ்வளவு உயரம் இருக்கு? கணுக்கால், முட்டி, இடுப்பு, இல்ல நெஞ்சு அளவா?",
        "water2": "தண்ணீர் முட்டிக்கு மேல இருக்கா? ஆமா இல்லன்னு சொல்லுங்க.",
        "readback": "ஒரு தடவை செக் பண்றேன்: {details}. சரியா?",
        "ask_correction": "எது தப்பா இருக்கு? சொல்லுங்க, சரி பண்றேன்.",
        "close": "உங்க விஷயத்தை எழுதிட்டோம், டிக்கெட் நம்பர் {digits}. ஒரு ஆபீசர் பார்ப்பாங்க, டீம் அனுப்புவோம். உயரமான, சேஃபான இடத்துலயே இருங்க, தண்ணீர்ல நடக்காதீங்க, போன் பேட்டரியை சேவ் பண்ணுங்க.",
        "close_callback": "உங்க விஷயத்தை எழுதிட்டோம், டிக்கெட் நம்பர் {digits}. நீங்க எங்க இருக்கீங்கன்னு கன்ஃபர்ம் பண்ண ஒரு ஆபீசர் கூப்பிடுவாங்க. போனை கையிலயே வெச்சுக்கோங்க, பேட்டரியை சேவ் பண்ணுங்க.",
        "urgent": "உங்க கேஸ் ரொம்ப அர்ஜென்ட்னு குறிச்சிருக்கோம், ஆபீசர்கிட்ட இப்பவே சொல்றோம்.",
        "people": "{n} பேர்", "person": "1 பேர்", "including": "{list} உட்பட",
        "at": "{address}", "near": "{landmark} பக்கத்துல", "door": "கதவு எண் {x}",
        "floor_n": "{n}வது மாடி", "ground": "தரை தளம்", "terrace": "மொட்டை மாடி", "pin": "பின் கோடு {x}",
        "none": "இன்னும் விவரம் இல்ல", "sep": ", ",
    },
    "hi-IN": {
        "ack": "ठीक है।",
        "not_heard": "माफ़ कीजिए, आवाज़ नहीं आई। फिर से बोलिए।",
        "calm": "मैं आपके साथ हूँ। एक लंबी साँस लीजिए, हम साथ में देख लेंगे।",
        "ans_when_help": "टाइम पक्का नहीं बता सकती, पर आपकी बात अभी टीम तक जा रही है।",
        "ans_stay_or_move": "जहाँ हैं वहीं रहिए। हो सके तो सबसे ऊपर वाले फ्लोर या छत पर जाइए। पानी में मत चलिए।",
        "ans_electricity": "तार और स्विच से दूर रहिए। पानी के पास बिजली की कोई चीज़ मत छूइए।",
        "ans_animal": "धीरे से उससे दूर हो जाइए और ऊँची जगह पर रहिए। टीम आए तो उन्हें बताइए।",
        "handoff": "मैं आपकी कॉल एक ऑफिसर को दे रही हूँ। आप लाइन में हैं, फ़ोन मत काटिए। आपका टिकट नंबर {digits} है।",
        "danger1": "किसी को चोट लगी है, या पानी तेज़ी से बढ़ रहा है?",
        "danger2": "किसी को चोट लगी है? हाँ या ना बोलिए।",
        "area1": "आप कहाँ हैं? एरिया और गली का नाम बताइए।",
        "area2": "बस एरिया का नाम बताइए, या पास में कोई बड़ा मंदिर, स्कूल या बस स्टॉप।",
        "area3": "आस-पास कोई मंदिर, स्कूल, पानी की टंकी या ऊँची बिल्डिंग दिख रही है? उसका नाम बताइए।",
        "again": "आराम से बताइए।",
        "rephrase": "आसान तरीके से पूछती हूँ।",
        "go_ahead": "हाँ, बताइए।",
        "p0_wait": "आपका टिकट नंबर {digits} है। मैं अभी ऑफिसर को बुला रही हूँ। फ़ोन मत काटिए।",
        "p1_wait": "आपका टिकट नंबर {digits} है। एक ऑफिसर आपसे बात करेंगे। लाइन पर रहिए, या बैटरी बचाने के लिए फ़ोन रख दीजिए: आपकी बारी नहीं जाएगी, हम इसी नंबर पर कॉल करेंगे।",
        "still_in_line": "आप अभी भी ऑफिसर के लिए लाइन में हैं। फ़ोन मत काटिए।",
        "request_human_ack": "आप ऑफिसर के लिए लाइन में हैं। तब तक एक सवाल।",
        "anger_ack": "मैं सुन रही हूँ। मदद के लिए आपकी बात आगे भेज रही हूँ।",
        "yes_automated": "हाँ, मैं एक ऑटोमैटिक असिस्टेंट हूँ। आप ऑफिसर के लिए लाइन में हैं।",
        "status_deflect": "इस लाइन पर मैं अपडेट या टाइम नहीं बता सकती। आपकी बात लिख ली गई है।",
        "new_info": "कोई नई बात पता चली है?",
        "noted": "लिख लिया।",
        "one_person": "फ़ोन एक ही इंसान को दीजिए, और मुँह के पास रखकर बोलिए।",
        "street1": "कौन सी गली, और घर नंबर या बिल्डिंग का नाम क्या है? आप कौन से फ्लोर पर हैं?",
        "street2": "घर के पास कोई बड़ा मंदिर, स्कूल, चर्च या दुकान है?",
        "floor1": "आप कौन से फ्लोर पर हैं?",
        "people1": "आपको मिलाकर वहाँ कितने लोग हैं?",
        "people2": "बस बताइए, कितने लोग हैं।",
        "vulnerable1": "साथ में कोई बड़े-बूढ़े, छोटे बच्चे, प्रेग्नेंट औरत, बीमार, या चल न पाने वाला कोई है?",
        "vulnerable2": "कोई बड़े-बूढ़े या बच्चे साथ हैं? हाँ या ना।",
        "vulnerable_who1": "कौन है? बड़े-बूढ़े, बच्चा, प्रेग्नेंट औरत, या कोई बीमार?",
        "water1": "पानी कितना ऊपर है? पैर तक, घुटने तक, कमर तक या छाती तक?",
        "water2": "पानी घुटने से ऊपर है? हाँ या ना।",
        "readback": "एक बार चेक कर लूँ: {details}। सही है?",
        "ask_correction": "क्या गलत है? बताइए, ठीक कर देती हूँ।",
        "close": "आपकी बात लिख ली गई है, टिकट नंबर {digits}। एक ऑफिसर इसे देखेंगे, और टीम भेजी जाएगी। किसी ऊँची और सेफ़ जगह पर रहिए, पानी में मत चलिए, और फ़ोन की बैटरी बचाइए।",
        "close_callback": "आपकी बात लिख ली गई है, टिकट नंबर {digits}। आप कहाँ हैं, ये पक्का करने के लिए एक ऑफिसर आपको कॉल करेंगे। फ़ोन पास रखिए और बैटरी बचाइए।",
        "urgent": "आपका केस सबसे ज़रूरी है, ऑफिसर को अभी बताया जा रहा है।",
        "people": "{n} लोग", "person": "1 इंसान", "including": "{list} के साथ",
        "at": "{address}", "near": "{landmark} के पास", "door": "घर नंबर {x}",
        "floor_n": "{n} फ्लोर", "ground": "ग्राउंड फ्लोर", "terrace": "छत", "pin": "पिन कोड {x}",
        "none": "अभी कुछ पता नहीं", "sep": ", ",
    },
    "te-IN": {
        "ack": "సరే.",
        "not_heard": "సారీ, సరిగ్గా వినపడలేదు. మళ్ళీ చెప్పండి.",
        "calm": "నేను మీతోనే ఉన్నాను. ఒకసారి గట్టిగా ఊపిరి తీసుకోండి, కలిసి చూద్దాం.",
        "ans_when_help": "టైమ్ కరెక్ట్‌గా చెప్పలేను, కానీ మీ విషయం ఇప్పుడే టీమ్‌కి వెళ్తోంది.",
        "ans_stay_or_move": "ఉన్న చోటే ఉండండి. వీలైతే పై ఫ్లోర్‌కి లేదా టెర్రస్‌కి వెళ్ళండి. నీళ్ళలో నడవకండి.",
        "ans_electricity": "వైర్లు, స్విచ్‌లకి దూరంగా ఉండండి. నీళ్ళ దగ్గర కరెంట్ వస్తువులు ముట్టుకోకండి.",
        "ans_animal": "నెమ్మదిగా దాని నుంచి దూరంగా వెళ్ళి, ఎత్తు చోట ఉండండి. టీమ్ వచ్చాక వాళ్ళకి చెప్పండి.",
        "handoff": "మీ కాల్ ఒక ఆఫీసర్‌కి ఇస్తున్నాను. మీరు లైన్‌లో ఉన్నారు, ఫోన్ పెట్టేయకండి. మీ టికెట్ నంబర్ {digits}.",
        "danger1": "ఎవరికైనా దెబ్బ తగిలిందా? లేక నీళ్ళు వేగంగా పెరుగుతున్నాయా?",
        "danger2": "ఎవరికైనా దెబ్బ తగిలిందా? అవును లేదా లేదు చెప్పండి.",
        "area1": "మీరు ఎక్కడ ఉన్నారు? ఏరియా పేరు, వీధి పేరు చెప్పండి.",
        "area2": "ఏరియా పేరు చాలు, లేదా దగ్గర్లో ఏదైనా పెద్ద గుడి, స్కూల్, బస్ స్టాప్ చెప్పండి.",
        "area3": "దగ్గర్లో గుడి, స్కూల్, వాటర్ ట్యాంక్ లేదా పెద్ద బిల్డింగ్ ఏదైనా కనిపిస్తుందా? దాని పేరు చెప్పండి.",
        "again": "నెమ్మదిగా చెప్పండి.",
        "rephrase": "ఈజీగా మళ్ళీ అడుగుతాను.",
        "go_ahead": "అవును, చెప్పండి.",
        "p0_wait": "మీ టికెట్ నంబర్ {digits}. ఇప్పుడే ఆఫీసర్‌కి చెప్తున్నాను. ఫోన్ పెట్టేయకండి.",
        "p1_wait": "మీ టికెట్ నంబర్ {digits}. ఒక ఆఫీసర్ మీతో మాట్లాడతారు. లైన్‌లో ఉండండి, లేదా బ్యాటరీ కోసం ఫోన్ పెట్టేయండి: మీ వంతు పోదు, ఇదే నంబర్‌కి కాల్ చేస్తాం.",
        "still_in_line": "మీరు ఇంకా ఆఫీసర్ కోసం లైన్‌లోనే ఉన్నారు. ఫోన్ పెట్టేయకండి.",
        "request_human_ack": "మీరు ఆఫీసర్ కోసం లైన్‌లో ఉన్నారు. అప్పటిదాకా ఒక ప్రశ్న.",
        "anger_ack": "నేను వింటున్నాను. మీకు సాయం అందేలా మీ విషయం పంపిస్తున్నాను.",
        "yes_automated": "అవును, నేను ఆటోమేటిక్ అసిస్టెంట్‌ని. మీరు ఆఫీసర్ కోసం లైన్‌లోనే ఉన్నారు.",
        "status_deflect": "ఈ లైన్‌లో అప్‌డేట్ గానీ టైమ్ గానీ చెప్పలేను. మీ విషయం రాసుకున్నాం.",
        "new_info": "ఏదైనా కొత్త విషయం తెలిసిందా?",
        "noted": "రాసుకున్నాను.",
        "one_person": "ఫోన్ ఒక్కరికే ఇవ్వండి, నోటి దగ్గర పెట్టుకుని మాట్లాడండి.",
        "street1": "ఏ వీధి, ఇంటి నంబర్ లేదా బిల్డింగ్ పేరు ఏంటి? మీరు ఏ ఫ్లోర్‌లో ఉన్నారు?",
        "street2": "మీ ఇంటి దగ్గర ఏదైనా పెద్ద గుడి, స్కూల్, చర్చి లేదా షాప్ ఉందా?",
        "floor1": "మీరు ఏ ఫ్లోర్‌లో ఉన్నారు?",
        "people1": "మీతో కలిపి ఎంత మంది ఉన్నారు?",
        "people2": "ఎంత మంది ఉన్నారో నంబర్ చెప్పండి చాలు.",
        "vulnerable1": "మీతో పెద్దవాళ్ళు, చిన్నపిల్లలు, కడుపుతో ఉన్నవాళ్ళు, ఒంట్లో బాలేనివాళ్ళు, లేదా నడవలేనివాళ్ళు ఎవరైనా ఉన్నారా?",
        "vulnerable2": "పెద్దవాళ్ళు లేదా పిల్లలు ఎవరైనా ఉన్నారా? అవును లేదా లేదు.",
        "vulnerable_who1": "ఎవరు? పెద్దవాళ్ళా, పిల్లలా, కడుపుతో ఉన్నవాళ్ళా, లేక ఒంట్లో బాలేనివాళ్ళా?",
        "water1": "నీళ్ళు ఎంత వరకు ఉన్నాయి? కాళ్ళ వరకా, మోకాళ్ళ వరకా, నడుము వరకా, ఛాతీ వరకా?",
        "water2": "నీళ్ళు మోకాళ్ళ పైకి ఉన్నాయా? అవును లేదా లేదు.",
        "readback": "ఒకసారి చెక్ చేస్తాను: {details}. కరెక్టేనా?",
        "ask_correction": "ఏది తప్పు? చెప్పండి, సరిచేస్తాను.",
        "close": "మీ విషయం రాసుకున్నాం, టికెట్ నంబర్ {digits}. ఒక ఆఫీసర్ చూస్తారు, టీమ్‌ని పంపిస్తాం. ఎత్తుగా, సేఫ్‌గా ఉన్న చోటే ఉండండి, నీళ్ళలో నడవకండి, ఫోన్ బ్యాటరీ సేవ్ చేయండి.",
        "close_callback": "మీ విషయం రాసుకున్నాం, టికెట్ నంబర్ {digits}. మీరు ఎక్కడ ఉన్నారో కన్ఫర్మ్ చేయడానికి ఒక ఆఫీసర్ కాల్ చేస్తారు. ఫోన్ దగ్గరే పెట్టుకోండి, బ్యాటరీ సేవ్ చేయండి.",
        "urgent": "మీ కేసు చాలా అర్జెంట్ అని పెట్టాం, ఆఫీసర్‌కి ఇప్పుడే చెప్తున్నాం.",
        "people": "{n} మంది", "person": "ఒక్కరు", "including": "{list} తో కలిపి",
        "at": "{address}", "near": "{landmark} దగ్గర", "door": "ఇంటి నంబర్ {x}",
        "floor_n": "{n} ఫ్లోర్", "ground": "గ్రౌండ్ ఫ్లోర్", "terrace": "టెర్రస్", "pin": "పిన్ కోడ్ {x}",
        "none": "ఇంకా వివరాలు లేవు", "sep": ", ",
    },
}

VULNERABLE_WORDS = {
    "en-IN": {"elderly": "elderly", "child": "child", "infant": "baby", "pregnant": "pregnant woman",
              "disabled": "disabled person", "sick": "sick person", "unspecified": "someone vulnerable"},
    "ta-IN": {"elderly": "வயசானவங்க", "child": "குழந்தைங்க", "infant": "கைக்குழந்தை", "pregnant": "கர்ப்பிணி",
              "disabled": "நடக்க முடியாதவங்க", "sick": "உடம்பு சரியில்லாதவங்க", "unspecified": "உதவி தேவைப்படுறவங்க"},
    "hi-IN": {"elderly": "बड़े-बूढ़े", "child": "बच्चे", "infant": "छोटा बच्चा", "pregnant": "प्रेग्नेंट औरत",
              "disabled": "चल न पाने वाले", "sick": "बीमार", "unspecified": "कोई कमज़ोर"},
    "te-IN": {"elderly": "పెద్దవాళ్ళు", "child": "పిల్లలు", "infant": "చిన్న బిడ్డ", "pregnant": "కడుపుతో ఉన్నవాళ్ళు",
              "disabled": "నడవలేనివాళ్ళు", "sick": "ఒంట్లో బాలేనివాళ్ళు", "unspecified": "సాయం కావాల్సినవాళ్ళు"},
}

ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
                 "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10}
ORDINALS = {
    "en-IN": {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"},
    "ta-IN": {1: "முதல் மாடி", 2: "இரண்டாவது மாடி", 3: "மூணாவது மாடி", 4: "நாலாவது மாடி", 5: "அஞ்சாவது மாடி"},
    "hi-IN": {1: "पहला फ्लोर", 2: "दूसरा फ्लोर", 3: "तीसरा फ्लोर", 4: "चौथा फ्लोर", 5: "पाँचवाँ फ्लोर"},
    "te-IN": {1: "ఫస్ట్ ఫ్లోర్", 2: "సెకండ్ ఫ్లోర్", 3: "థర్డ్ ఫ్లోర్", 4: "ఫోర్త్ ఫ్లోర్", 5: "ఫిఫ్త్ ఫ్లోర్"},
}


def _p(lang: str) -> dict[str, str]:
    return PHRASES.get(lang, PHRASES["en-IN"])


def say(key: str, lang: str, **kw) -> str:
    return _p(lang)[key].format(**kw)


def has(key: str, lang: str) -> bool:
    return key in _p(lang)


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
        # digits one by one, so the voice reads "6 0 0 0 4 2", not "six lakh..."
        p["pin"].format(x=" ".join(loc.pincode)) if getattr(loc, "pincode", None) else None,
        floor_text(loc.floor, lang),
    ]
    addr_text = p["sep"].join(a for a in addr if a)
    if addr_text:
        bits.append(p["at"].format(address=addr_text))
    landmark = loc.landmark_native if native and loc.landmark_native else loc.landmark
    if landmark:
        bits.append(p["near"].format(landmark=landmark))
    return p["sep"].join(bits) or p["none"]