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
        # said in turn after a plain answer, so the caller doesn't hear the same word every time
        "ack2": "Got it.", "ack3": "Yes, noted.",
        # once a call, when the caller has said nobody is hurt and nothing about the case is urgent
        "relief": "Thank goodness everyone is all right.",
        "not_heard": "Sorry, the line cut out. Could you say that once more?",
        "calm": "I am right here, listening. I will ask short questions, you just keep answering.",
        "ans_when_help": "I can't give an exact time, but your request is going to the rescue teams right now.",
        "ans_stay_or_move": "Do not go out into the water. If you can, move up to a higher floor or the terrace.",
        "ans_electricity": "Stay away from wires and switches. Do not touch anything electrical near the water.",
        "ans_animal": "Move away from it slowly and stay on higher ground. Tell the rescue team when they come.",
        "handoff": "I am passing your call to an officer. An officer will speak to you when one is free, please stay on the phone. Your ticket number is {digits}.",
        "danger1": "Is anyone hurt? And is the water rising fast?",
        "danger2": "Is anyone hurt or not? Just tell me that.",
        "area1": "Now tell me, where is help needed? The area and the street name.",
        "area2": "Tell me the area name. If you don't know it, tell me any big temple, school or bus stop nearby.",
        "area3": "What can you see around you? A temple, a school, a water tank, a tall building? Tell me its name.",
        "again": "Take your time.",
        "rephrase": "Sorry, let me ask that another way.",
        "go_ahead": "Yes, please tell me.",
        "p0_wait": "Your ticket number is {digits}. An officer is being alerted now. Stay on the line.",
        "p1_wait": "Your ticket number is {digits}. An officer will speak to you when one is free, stay on the line. If your battery is low you can hang up, your request stays with us.",
        "still_in_line": "I am right here, the line is open. An officer will speak to you when one is free.",
        "request_human_ack": "Yes, an officer will speak to you when one is free. Until then I will write down your details, so you don't have to repeat them.",
        "anger_ack": "I am sorry you are going through this. I am getting your details straight to the team.",
        "yes_automated": "Yes, I am an automated assistant, not a person. But everything you say is showing on the control room's screen.",
        "status_deflect": "I don't know the time, and I won't give you a false one. All your details are on the control room's screen.",
        "new_info": "Do you have any new information?",
        "noted": "Noted.",
        "one_person": "The line is breaking up. Hold the phone close to your mouth, and one person at a time, please.",
        "street1": "Which street is it? And the house number, or the building name?",
        "street2": "Is there a big place near the house? A temple, a school, a church or a shop?",
        "floor1": "Which floor?",
        "people1": "And how many people are there, all together?",
        "people2": "How many people are there? Just the count is fine.",
        "vulnerable1": "Is anyone among them elderly, or a small child? Or pregnant, sick, or not able to walk?",
        "vulnerable2": "Are there any old people or children there, or not? Just tell me that.",
        "vulnerable_who1": "Who are they? Elderly, a child, pregnant, or sick?",
        "water1": "How far has the water come up? To the ankle, the knee, the waist, or the chest?",
        "water2": "Has the water come above the knee? Just tell me yes or no.",
        "readback": "Let me say that back once. {details}. Is that right?",
        "ask_correction": "Which part is wrong? Tell me and I will fix it right away.",
        "close": "Your ticket number is {digits}. All your details have reached the control room, an officer will review them and send a team. Until then stay somewhere high and safe, do not step into the water, and save your battery.",
        "close_callback": "Your ticket number is {digits}. Your details have reached the control room. An officer may need to speak to you to confirm where you are, so keep the phone with you and save your battery.",
        "urgent": "Your case is marked most urgent and a rescue officer is being alerted now.",
        # read-back pieces
        "people": "{n} people", "person": "1 person", "including": "including {list}",
        # the address from the area down to the house ("big") or the other way ("small"), and the floor
        "addr_order": "small", "on_floor": "{floor}",
        "at": "at {address}", "near": "near {landmark}", "door": "door number {x}",
        "floor_n": "{n} floor", "ground": "ground floor", "terrace": "terrace", "pin": "pin code {x}",
        "none": "no details yet", "sep": ", ",
    },
    "ta-IN": {
        "ack": "சரி.",
        # said in turn after a plain answer, so the caller doesn't hear the same word every time
        "ack2": "புரிஞ்சுது.", "ack3": "சரி, எழுதிக்கிட்டேன்.",
        # once a call, when the caller has said nobody is hurt and nothing about the case is urgent
        "relief": "நல்ல வேளை, யாருக்கும் ஒண்ணும் ஆகல.",
        "not_heard": "சாரி, லைன் கட் ஆச்சு. இன்னொரு தடவை சொல்றீங்களா?",
        "calm": "நான் இங்கதான் இருக்கேன், நீங்க சொல்றதை கேக்கறேன். சின்ன சின்ன கேள்வி கேக்கறேன், நீங்க பதில் சொல்லிட்டே இருங்க.",
        "ans_when_help": "டைம் சரியா சொல்ல முடியாது, ஆனா உங்க விஷயம் இப்பவே டீமுக்கு போயிட்டு இருக்கு.",
        "ans_stay_or_move": "வெளிய தண்ணீர்ல போகாதீங்க. முடிஞ்சா மேல் மாடிக்கோ மொட்டை மாடிக்கோ போங்க.",
        "ans_electricity": "வயர், சுவிட்ச் பக்கம் போகாதீங்க. தண்ணீர் பக்கத்துல எந்த மின்சார பொருளையும் தொடாதீங்க.",
        "ans_animal": "மெதுவா அதுகிட்ட இருந்து விலகி, உயரமான இடத்துல இருங்க. டீம் வந்தா சொல்லுங்க.",
        "handoff": "உங்க காலை ஒரு ஆபீசர்கிட்ட கொடுக்கறேன். ஆபீசர் ஃப்ரீ ஆனதும் பேசுவாங்க, போனை வெக்காதீங்க. உங்க டிக்கெட் நம்பர் {digits}.",
        "danger1": "யாருக்கும் அடிபடலையே? தண்ணீர் வேகமா ஏறலையே?",
        "danger2": "யாருக்காவது அடிபட்டிருக்கா, இல்லையா? அதை மட்டும் சொல்லுங்க.",
        "area1": "இப்ப சொல்லுங்க, உதவி எங்க வேணும்? ஏரியா பேரும் தெரு பேரும் சொல்லுங்க.",
        "area2": "ஏரியா பேர் சொல்லுங்க. தெரியலன்னா பக்கத்துல ஏதாவது பெரிய கோவில், ஸ்கூல், பஸ் ஸ்டாப் சொல்லுங்க.",
        "area3": "சுத்தி என்ன தெரியுது? கோவில், ஸ்கூல், தண்ணீர் தொட்டி, பெரிய கட்டடம் ஏதாவது? அதோட பேர் சொல்லுங்க.",
        "again": "நிதானமா சொல்லுங்க.",
        "rephrase": "சாரி, வேற மாதிரி கேக்கறேன்.",
        "go_ahead": "சரி, சொல்லுங்க.",
        "p0_wait": "உங்க டிக்கெட் நம்பர் {digits}. இப்பவே ஆபீசர்கிட்ட சொல்றேன். போனை வெக்காதீங்க.",
        "p1_wait": "உங்க டிக்கெட் நம்பர் {digits}. ஆபீசர் ஃப்ரீ ஆனதும் உங்ககிட்ட பேசுவாங்க, லைன்லயே இருங்க. பேட்டரி கம்மியா இருந்தா போனை வெச்சிடலாம், உங்க ரிக்வெஸ்ட் அப்படியே இருக்கும்.",
        "still_in_line": "நான் இங்கதான் இருக்கேன், லைன் ஆன்லதான் இருக்கு. ஆபீசர் ஃப்ரீ ஆனதும் உங்ககிட்ட பேசுவாங்க.",
        "request_human_ack": "சரி, ஆபீசர் ஃப்ரீ ஆனதும் உங்ககிட்ட பேசுவாங்க. அதுவரை உங்க விவரத்தை எழுதிக்கறேன், நீங்க மறுபடியும் சொல்ல வேண்டாம்.",
        "anger_ack": "சாரி, நீங்க இவ்வளவு கஷ்டப்படறீங்க. உங்க விஷயத்தை நேரா டீமுக்கு அனுப்பறேன்.",
        "yes_automated": "ஆமா, நான் ஆட்டோமேட்டிக் அசிஸ்டன்ட், மனுஷன் இல்ல. ஆனா நீங்க சொல்றது எல்லாம் கண்ட்ரோல் ரூம் ஸ்கிரீன்ல தெரியுது.",
        "status_deflect": "டைம் எனக்கு தெரியாது, தப்பான டைம் சொல்ல மாட்டேன். உங்க விவரம் எல்லாம் கண்ட்ரோல் ரூம் ஸ்கிரீன்ல இருக்கு.",
        "new_info": "ஏதாவது புது விஷயம் தெரிஞ்சுதா?",
        "noted": "குறிச்சுக்கிட்டேன்.",
        "one_person": "குரல் கட் ஆகி கட் ஆகி வருது. போனை வாய்க்கு பக்கத்துல வெச்சுக்கோங்க, ஒரு நேரத்துல ஒருத்தர் மட்டும் பேசுங்க.",
        "street1": "எந்த தெரு? வீட்டு நம்பர், இல்ல அபார்ட்மெண்ட் பேர்?",
        "street2": "வீட்டு பக்கத்துல ஏதாவது பெரிய இடம் இருக்கா? கோவில், ஸ்கூல், சர்ச், கடை மாதிரி?",
        "floor1": "எந்த மாடி?",
        "people1": "அங்க எல்லாரும் சேர்த்து எத்தனை பேர் இருக்காங்க?",
        "people2": "அங்க எத்தனை பேர் இருக்காங்க? எண்ணிக்கை மட்டும் சொன்னா போதும்.",
        "vulnerable1": "அவங்கள்ல வயசானவங்க இல்ல சின்ன குழந்தை இருக்காங்களா? இல்ல கர்ப்பிணி, உடம்பு சரியில்லாதவங்க, நடக்க முடியாதவங்க யாராவது?",
        "vulnerable2": "அங்க வயசானவங்க இல்ல குழந்தை இருக்காங்களா, இல்லையா? அதை மட்டும் சொல்லுங்க.",
        "vulnerable_who1": "யாரு அவங்க? வயசானவங்களா, குழந்தையா, கர்ப்பிணியா, இல்ல உடம்பு சரியில்லாதவங்களா?",
        "water1": "தண்ணீர் எது வரைக்கும் வந்திருக்கு? கணுக்கால், முட்டி, இடுப்பு, இல்ல நெஞ்சு வரைக்குமா?",
        "water2": "தண்ணீர் முட்டிக்கு மேல வந்திருக்கா? ஆமாவா இல்லையான்னு சொல்லுங்க.",
        "readback": "ஒரு தடவை திரும்ப சொல்றேன். {details}. சரியா?",
        "ask_correction": "எந்த விஷயம் தப்பா இருக்கு? சொல்லுங்க, இப்பவே சரி பண்றேன்.",
        "close": "உங்க டிக்கெட் நம்பர் {digits}. உங்க விவரம் எல்லாம் கண்ட்ரோல் ரூமுக்கு போயிடுச்சு, ஆபீசர் பார்த்துட்டு டீம் அனுப்புவாங்க. அதுவரை உயரமான, சேஃபான இடத்துலயே இருங்க, தண்ணீர்ல இறங்காதீங்க, பேட்டரியை பார்த்து யூஸ் பண்ணுங்க.",
        "close_callback": "உங்க டிக்கெட் நம்பர் {digits}. உங்க விவரம் கண்ட்ரோல் ரூமுக்கு போயிடுச்சு. நீங்க எங்க இருக்கீங்கன்னு கன்ஃபர்ம் பண்ண ஆபீசர் உங்ககிட்ட பேச வேண்டி வரலாம், அதனால போனை கையிலயே வெச்சுக்கோங்க, பேட்டரியை பார்த்து யூஸ் பண்ணுங்க.",
        "urgent": "உங்க கேஸ் ரொம்ப அர்ஜென்ட்னு குறிச்சிருக்கோம், ஆபீசர்கிட்ட இப்பவே சொல்றோம்.",
        "people": "{n} பேர் இருக்காங்க", "person": "ஒருத்தர் மட்டும் இருக்காங்க", "including": "{list} உட்பட",
        # the address from the area down to the house ("big") or the other way ("small"), and the floor
        "addr_order": "big", "on_floor": "{floor}",
        "at": "{address}", "near": "{landmark} பக்கத்துல", "door": "கதவு எண் {x}",
        "floor_n": "{n}வது மாடி", "ground": "தரை தளம்", "terrace": "மொட்டை மாடி", "pin": "பின் கோடு {x}",
        "none": "இன்னும் விவரம் இல்ல", "sep": ", ",
    },
    "hi-IN": {
        "ack": "ठीक है।",
        # said in turn after a plain answer, so the caller doesn't hear the same word every time
        "ack2": "समझ गई।", "ack3": "हाँ, लिख लिया।",
        # once a call, when the caller has said nobody is hurt and nothing about the case is urgent
        "relief": "शुक्र है, सब ठीक हैं।",
        "not_heard": "सॉरी, आवाज़ कट गई थी। एक बार फिर से बोलेंगे?",
        "calm": "मैं यहीं हूँ, आपकी बात सुन रही हूँ। छोटे-छोटे सवाल पूछूँगी, आप बस जवाब देते जाइए।",
        "ans_when_help": "टाइम पक्का नहीं बता सकती, पर आपकी बात अभी टीम तक जा रही है।",
        "ans_stay_or_move": "घर से बाहर पानी में मत निकलिए। हो सके तो ऊपर वाले फ्लोर या छत पर चले जाइए।",
        "ans_electricity": "तार और स्विच से दूर रहिए। पानी के पास बिजली की कोई चीज़ मत छूइए।",
        "ans_animal": "धीरे से उससे दूर हो जाइए और ऊँची जगह पर रहिए। टीम आए तो उन्हें बताइए।",
        "handoff": "मैं आपकी कॉल एक ऑफिसर को दे रही हूँ। ऑफिसर फ़्री होते ही बात करेंगे, फ़ोन मत काटिए। आपका टिकट नंबर {digits} है।",
        "danger1": "किसी को चोट तो नहीं लगी? और पानी तेज़ी से बढ़ तो नहीं रहा?",
        "danger2": "किसी को चोट लगी है या नहीं? इतना बता दीजिए।",
        "area1": "अब बताइए, मदद कहाँ चाहिए? एरिया और गली का नाम बता दीजिए।",
        "area2": "एरिया का नाम बता दीजिए। नहीं पता तो पास का कोई बड़ा मंदिर, स्कूल या बस स्टॉप बताइए।",
        "area3": "आस-पास क्या दिख रहा है? कोई मंदिर, स्कूल, पानी की टंकी या ऊँची बिल्डिंग? उसका नाम बता दीजिए।",
        "again": "आराम से बताइए।",
        "rephrase": "सॉरी, मैं दूसरे तरीके से पूछती हूँ।",
        "go_ahead": "हाँ, बताइए।",
        "p0_wait": "आपका टिकट नंबर है {digits}। मैं अभी ऑफिसर को बुला रही हूँ, फ़ोन मत काटिए।",
        "p1_wait": "आपका टिकट नंबर {digits} है। ऑफिसर फ़्री होते ही आपसे बात करेंगे, लाइन पर रहिए। बैटरी कम हो तो फ़ोन रख सकते हैं, आपकी रिक्वेस्ट बनी रहेगी।",
        "still_in_line": "मैं यहीं हूँ, लाइन चालू है। ऑफिसर फ़्री होते ही आपसे बात करेंगे।",
        "request_human_ack": "जी, ऑफिसर फ़्री होते ही आपसे बात करेंगे। तब तक मैं आपकी जानकारी लिख लेती हूँ, ताकि आपको दोबारा न बतानी पड़े।",
        "anger_ack": "सॉरी, आपको ये सब झेलना पड़ रहा है। मैं आपकी बात सीधे टीम को भेज रही हूँ।",
        "yes_automated": "हाँ, मैं ऑटोमैटिक असिस्टेंट हूँ, इंसान नहीं। पर आपकी हर बात कंट्रोल रूम की स्क्रीन पर दिख रही है।",
        "status_deflect": "टाइम मुझे नहीं पता, और झूठा टाइम मैं नहीं बताऊँगी। आपकी पूरी जानकारी कंट्रोल रूम की स्क्रीन पर है।",
        "new_info": "क्या कोई नई बात पता चली है?",
        "noted": "लिख लिया।",
        "one_person": "आवाज़ कट-कट कर आ रही है। फ़ोन मुँह के पास रखिए, और एक बार में एक ही इंसान बोलिए।",
        "street1": "गली कौन सी है? और घर का नंबर, या बिल्डिंग का नाम?",
        "street2": "घर के पास कोई बड़ी जगह है? जैसे मंदिर, स्कूल, चर्च या कोई दुकान?",
        "floor1": "कौन से फ्लोर पर हैं?",
        "people1": "और वहाँ कितने लोग हैं, सब मिलाकर?",
        "people2": "कितने लोग हैं वहाँ? सिर्फ़ गिनती बता दीजिए।",
        "vulnerable1": "इनमें कोई बड़े-बूढ़े या छोटा बच्चा है? या कोई प्रेग्नेंट, बीमार, या जो चल नहीं पाते?",
        "vulnerable2": "वहाँ कोई बड़े-बूढ़े या बच्चे हैं या नहीं? इतना बता दीजिए।",
        "vulnerable_who1": "कौन हैं वो? कोई बड़े-बूढ़े, बच्चा, प्रेग्नेंट, या बीमार?",
        "water1": "पानी कहाँ तक आ गया है? पैर तक, घुटने तक, कमर तक, या छाती तक?",
        "water2": "पानी घुटने से ऊपर आ गया है क्या? हाँ या ना में बता दीजिए।",
        "readback": "एक बार दोहरा देती हूँ। {details}। क्या ये सही है?",
        "ask_correction": "कौन सी बात गलत है? बता दीजिए, अभी ठीक कर देती हूँ।",
        "close": "आपका टिकट नंबर है {digits}। सारी जानकारी कंट्रोल रूम को मिल गई है, ऑफिसर देखकर टीम भेजेंगे। तब तक ऊपर, सेफ़ जगह पर रहिए, पानी में मत उतरिए, और बैटरी बचाकर रखिए।",
        "close_callback": "आपका टिकट नंबर है {digits}। जानकारी कंट्रोल रूम को मिल गई है। जगह पक्की करने के लिए ऑफिसर को आपसे बात करनी पड़ सकती है, तो फ़ोन पास रखिए और बैटरी बचाकर रखिए।",
        "urgent": "आपका केस सबसे ज़रूरी है, ऑफिसर को अभी बताया जा रहा है।",
        "people": "{n} लोग हैं", "person": "1 इंसान है", "including": "जिनमें {list} हैं",
        # the address from the area down to the house ("big") or the other way ("small"), and the floor
        "addr_order": "big", "on_floor": "{floor} पर",
        "at": "{address}", "near": "{landmark} के पास", "door": "घर नंबर {x}",
        "floor_n": "{n} फ्लोर", "ground": "ग्राउंड फ्लोर", "terrace": "छत", "pin": "पिन कोड {x}",
        "none": "अभी कुछ पता नहीं", "sep": ", ",
    },
    "te-IN": {
        "ack": "సరే.",
        # said in turn after a plain answer, so the caller doesn't hear the same word every time
        "ack2": "అర్థమైంది.", "ack3": "సరే, రాసుకున్నాను.",
        # once a call, when the caller has said nobody is hurt and nothing about the case is urgent
        "relief": "హమ్మయ్య, అందరూ బాగానే ఉన్నారు.",
        "not_heard": "సారీ, లైన్ కట్ అయింది. ఇంకోసారి చెప్తారా?",
        "calm": "నేను ఇక్కడే ఉన్నాను, మీ మాట వింటున్నాను. చిన్న చిన్న ప్రశ్నలు అడుగుతాను, మీరు జవాబు చెప్తూ ఉండండి.",
        "ans_when_help": "టైమ్ కరెక్ట్‌గా చెప్పలేను, కానీ మీ విషయం ఇప్పుడే టీమ్‌కి వెళ్తోంది.",
        "ans_stay_or_move": "బయట నీళ్ళలోకి వెళ్ళకండి. వీలైతే పై ఫ్లోర్‌కి లేదా టెర్రస్‌కి వెళ్ళండి.",
        "ans_electricity": "వైర్లు, స్విచ్‌లకి దూరంగా ఉండండి. నీళ్ళ దగ్గర కరెంట్ వస్తువులు ముట్టుకోకండి.",
        "ans_animal": "నెమ్మదిగా దాని నుంచి దూరంగా వెళ్ళి, ఎత్తు చోట ఉండండి. టీమ్ వచ్చాక వాళ్ళకి చెప్పండి.",
        "handoff": "మీ కాల్ ఒక ఆఫీసర్‌కి ఇస్తున్నాను. ఆఫీసర్ ఫ్రీ అవ్వగానే మాట్లాడతారు, ఫోన్ పెట్టేయకండి. మీ టికెట్ నంబర్ {digits}.",
        "danger1": "ఎవరికీ దెబ్బలు తగల్లేదు కదా? నీళ్ళు వేగంగా పెరగడం లేదు కదా?",
        "danger2": "ఎవరికైనా దెబ్బ తగిలిందా, లేదా? అదొక్కటి చెప్పండి.",
        "area1": "ఇప్పుడు చెప్పండి, సాయం ఎక్కడ కావాలి? ఏరియా పేరు, వీధి పేరు చెప్పండి.",
        "area2": "ఏరియా పేరు చెప్పండి. తెలియకపోతే దగ్గర్లో ఏదైనా పెద్ద గుడి, స్కూల్, బస్ స్టాప్ చెప్పండి.",
        "area3": "చుట్టుపక్కల ఏం కనిపిస్తోంది? గుడి, స్కూల్, వాటర్ ట్యాంక్, పెద్ద బిల్డింగ్ ఏదైనా? దాని పేరు చెప్పండి.",
        "again": "నెమ్మదిగా చెప్పండి.",
        "rephrase": "సారీ, ఇంకోలా అడుగుతాను.",
        "go_ahead": "అవును, చెప్పండి.",
        "p0_wait": "మీ టికెట్ నంబర్ {digits}. ఇప్పుడే ఆఫీసర్‌కి చెప్తున్నాను. ఫోన్ పెట్టేయకండి.",
        "p1_wait": "మీ టికెట్ నంబర్ {digits}. ఆఫీసర్ ఫ్రీ అవ్వగానే మీతో మాట్లాడతారు, లైన్‌లో ఉండండి. బ్యాటరీ తక్కువ ఉంటే ఫోన్ పెట్టేయొచ్చు, మీ రిక్వెస్ట్ అలాగే ఉంటుంది.",
        "still_in_line": "నేను ఇక్కడే ఉన్నాను, లైన్ ఆన్‌లోనే ఉంది. ఆఫీసర్ ఫ్రీ అవ్వగానే మీతో మాట్లాడతారు.",
        "request_human_ack": "సరే, ఆఫీసర్ ఫ్రీ అవ్వగానే మీతో మాట్లాడతారు. అప్పటిదాకా మీ వివరాలు రాసుకుంటాను, మీరు మళ్ళీ చెప్పాల్సిన పని ఉండదు.",
        "anger_ack": "సారీ, మీరు ఇంత ఇబ్బంది పడుతున్నారు. మీ విషయం నేరుగా టీమ్‌కి పంపిస్తున్నాను.",
        "yes_automated": "అవును, నేను ఆటోమేటిక్ అసిస్టెంట్‌ని, మనిషిని కాదు. కానీ మీరు చెప్పేదంతా కంట్రోల్ రూమ్ స్క్రీన్ మీద కనిపిస్తోంది.",
        "status_deflect": "టైమ్ నాకు తెలీదు, తప్పు టైమ్ చెప్పను. మీ వివరాలన్నీ కంట్రోల్ రూమ్ స్క్రీన్ మీద ఉన్నాయి.",
        "new_info": "ఏదైనా కొత్త విషయం తెలిసిందా?",
        "noted": "రాసుకున్నాను.",
        "one_person": "మాట కట్ అవుతోంది. ఫోన్ నోటి దగ్గర పెట్టుకోండి, ఒకసారి ఒక్కరే మాట్లాడండి.",
        "street1": "వీధి ఏది? ఇంటి నంబర్, లేదా బిల్డింగ్ పేరు?",
        "street2": "ఇంటి దగ్గర ఏదైనా పెద్ద చోటు ఉందా? గుడి, స్కూల్, చర్చి, షాప్ లాంటిది?",
        "floor1": "ఏ ఫ్లోర్‌లో ఉన్నారు?",
        "people1": "అక్కడ అందరూ కలిపి ఎంత మంది ఉన్నారు?",
        "people2": "అక్కడ ఎంత మంది ఉన్నారు? లెక్క చెప్తే చాలు.",
        "vulnerable1": "వాళ్ళలో పెద్దవాళ్ళు గానీ, చిన్నపిల్లలు గానీ ఉన్నారా? లేదా కడుపుతో ఉన్నవాళ్ళు, ఒంట్లో బాలేనివాళ్ళు, నడవలేనివాళ్ళు ఎవరైనా?",
        "vulnerable2": "అక్కడ పెద్దవాళ్ళు గానీ పిల్లలు గానీ ఉన్నారా, లేరా? అదొక్కటి చెప్పండి.",
        "vulnerable_who1": "ఎవరు వాళ్ళు? పెద్దవాళ్ళా, పిల్లలా, కడుపుతో ఉన్నవాళ్ళా, లేక ఒంట్లో బాలేనివాళ్ళా?",
        "water1": "నీళ్ళు ఎంత వరకు వచ్చాయి? కాళ్ళ వరకా, మోకాళ్ళ వరకా, నడుము వరకా, ఛాతీ వరకా?",
        "water2": "నీళ్ళు మోకాళ్ళ పైకి వచ్చాయా? అవునో కాదో చెప్పండి.",
        "readback": "ఒకసారి మళ్ళీ చెప్తాను. {details}. కరెక్టేనా?",
        "ask_correction": "ఏ విషయం తప్పుగా ఉంది? చెప్పండి, ఇప్పుడే సరిచేస్తాను.",
        "close": "మీ టికెట్ నంబర్ {digits}. మీ వివరాలన్నీ కంట్రోల్ రూమ్‌కి చేరాయి, ఆఫీసర్ చూసి టీమ్‌ని పంపిస్తారు. అప్పటిదాకా ఎత్తుగా, సేఫ్‌గా ఉన్న చోటే ఉండండి, నీళ్ళలోకి దిగకండి, బ్యాటరీ జాగ్రత్తగా వాడండి.",
        "close_callback": "మీ టికెట్ నంబర్ {digits}. మీ వివరాలు కంట్రోల్ రూమ్‌కి చేరాయి. మీరు ఎక్కడ ఉన్నారో కన్ఫర్మ్ చేయడానికి ఆఫీసర్ మీతో మాట్లాడాల్సి రావచ్చు, అందుకే ఫోన్ దగ్గరే పెట్టుకోండి, బ్యాటరీ జాగ్రత్తగా వాడండి.",
        "urgent": "మీ కేసు చాలా అర్జెంట్ అని పెట్టాం, ఆఫీసర్‌కి ఇప్పుడే చెప్తున్నాం.",
        "people": "{n} మంది ఉన్నారు", "person": "ఒక్కరే ఉన్నారు", "including": "అందులో {list} ఉన్నారు",
        # the address from the area down to the house ("big") or the other way ("small"), and the floor
        "addr_order": "big", "on_floor": "{floor}",
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
    floor = floor_text(loc.floor, lang)
    parts = {
        "door": p["door"].format(x=loc.door_no) if loc.door_no else None,
        "building": (loc.building_native if native and loc.building_native else loc.building),
        "street": (loc.street_native if native and loc.street_native else loc.street),
        "area": native_name(loc.locality, lang),
        # digits one by one, so the voice reads "6 0 0 0 4 2", not "six lakh..."
        "pin": p["pin"].format(x=" ".join(loc.pincode)) if getattr(loc, "pincode", None) else None,
        "floor": p["on_floor"].format(floor=floor) if floor else None,
    }
    # Hindi, Telugu and Tamil speakers give an address from the area down to the house;
    # English goes the other way.
    order = (("area", "street", "building", "door", "floor", "pin") if p["addr_order"] == "big"
             else ("door", "building", "street", "area", "pin", "floor"))
    addr_text = p["sep"].join(parts[k] for k in order if parts[k])
    if addr_text:
        bits.append(p["at"].format(address=addr_text))
    landmark = loc.landmark_native if native and loc.landmark_native else loc.landmark
    if landmark:
        bits.append(p["near"].format(landmark=landmark))
    return p["sep"].join(bits) or p["none"]