/**
 * Your test calls, as simulated callers on the call screen. Unlike the other simulated callers,
 * these say their lines in order (like backend/my_calls/*.txt), keep talking while the call is in
 * line for an officer, and can break up (crack 1-3) like a bad phone line.
 *
 * One call tests one thing. Each summary ends with "Should:", what a good agent does on that call.
 * Callers talk the way people do on a phone (half sentences, "मैडम", "అండి"), in Hindi or Telugu;
 * six calls change language part-way (a phone handed over, a
 * frightened caller falling back to their own language). All callers, addresses and ticket
 * numbers are made up.
 */

const hi = (text, crack) => ({ lang: "hi-IN", text, crack });
const te = (text, crack) => ({ lang: "te-IN", text, crack });

export const TEST_CALLS = [
  // ------------------------------------------------------------------ the normal calls
  {
    id: "test-ideal-call",
    name: "01 Ideal call (Hindi)",
    summary: "Hindi caller who answers every question clearly, first time. "
      + "Should: ask each thing once, read it back, give the ticket number, end the call.",
    lang: "hi-IN",
    lines: [
      hi("नहीं नहीं, चोट किसी को नहीं लगी। पानी भी अभी रुका हुआ है।"),
      hi("अन्ना नगर में, सेकंड एवेन्यू, घर नंबर बयालीस।"),
      hi("नीचे ही, ग्राउंड फ्लोर पर।"),
      hi("तीन हैं हम।"),
      hi("नहीं जी, सब बड़े हैं, सब ठीक हैं।"),
      hi("घुटने तक है अभी।"),
      hi("हाँ हाँ, बिलकुल सही।"),
    ],
  },
  {
    id: "test-one-breath",
    name: "02 Everything in one breath (Telugu)",
    summary: "The caller gives the address, floor, people and water level in the first sentence. "
      + "Should: not ask for any of it again; ask only who is vulnerable, then read back.",
    lang: "te-IN",
    lines: [
      te("మేడం, ఎవరికీ ఏమీ కాలేదు. మేము కృష్ణలంకలో ఉంటాం, రాణిగారి తోట, ఇంటి నంబర్ నలభై, ఫస్ట్ ఫ్లోర్. నలుగురం ఉన్నాం, నీళ్ళు మోకాళ్ళ దాకా వచ్చాయి, ఇంకా పెరగట్లేదు."),
      te("ఆ, మా అత్తగారు ఉన్నారండి, డెబ్భై ఏళ్ళు, మెట్లు ఎక్కలేరు."),
      te("అవును, కరెక్టే అండి."),
      te("సరేనండి, లైన్‌లోనే ఉంటాను."),
    ],
  },
  {
    id: "test-code-mixed",
    name: "03 Hindi and English mixed",
    summary: "Every sentence mixes Hindi and English, and the water level is given as 'up to the stairs'. "
      + "Should: follow the mix, reply in Hindi, and not turn 'up to the stairs' into a guessed level.",
    lang: "hi-IN",
    lines: [
      hi("Hello, हाँ, हमारे घर में water घुस गया है, parking पूरी डूब गई। Injured कोई नहीं है।"),
      hi("Kondapur में, Botanical Garden road पे, flat number तीन सौ दो, third floor।"),
      hi("Four हैं हम, मैं, wife और दो kids।"),
      hi("हाँ kids छोटे हैं, एक five का, एक eight का।"),
      hi("Water first floor की stairs तक आ गया है, ground floor तो पूरा डूब गया।"),
      hi("हाँ हाँ, correct है।"),
    ],
  },
  {
    id: "test-pin-only",
    name: "04 Only knows the PIN code (Telugu)",
    summary: "New in the city: doesn't know the area name, offers the PIN code, asks 'shall I tell you?'. "
      + "Should: say yes to the PIN code, read it back digit by digit, never insist on an area name.",
    lang: "te-IN",
    lines: [
      te("ఇంట్లోకి నీళ్ళు వచ్చేస్తున్నాయండి. దెబ్బలేం తగల్లేదు ఎవరికీ."),
      te("ఏరియా పేరు తెలీదండి, నేనిక్కడికి కొత్త. పిన్ కోడ్ ఒక్కటే తెలుసు, పర్లేదా?"),
      te("ఐదు సున్నా సున్నా, సున్నా తొమ్మిది నాలుగు."),
      te("ఇంటి అడ్రస్ చెప్పనా?"),
      te("ఇంటి నంబర్ ఇరవై మూడు, సాయినాథ్ కాలనీ. సెకండ్ ఫ్లోర్‌లో ఉంటాం."),
      te("ఇద్దరమే."),
      te("లేరండి, ఎవరూ లేరు."),
      te("మోకాళ్ళ దాకా."),
      te("అవును, కరెక్టే."),
    ],
  },

  // ------------------------------------------------------------------ life in danger
  {
    id: "test-panic",
    name: "05 Panic: 'we are going to die' (Hindi, then Telugu)",
    summary: "Water at the neck, children crying. The caller starts in Hindi and falls back to Telugu when most "
      + "frightened, and doesn't know the area. "
      + "Should: follow into Telugu, one short calming line (never 'take a breath'), short questions, no "
      + "street or house-number question, no 'I can't give updates', and stay on the line for an officer.",
    lang: "hi-IN",
    lines: [
      hi("बचाओ! बचाओ! पानी गले तक आ गया है, बच्चे रो रहे हैं, हम मर जाएँगे!"),
      hi("अरे जल्दी करो ना! जल्दी किसी को भेजो!"),
      te("ఏ ఏరియానో నాకు తెలీదు! మేము ఇక్కడికి కొత్తగా వచ్చాం!"),
      te("ఎదురుగా పెద్ద వాటర్ ట్యాంక్ ఉంది, పక్కనే హనుమాన్ గుడి."),
      te("డాబా మీద ఉన్నాం! ఐదుగురం, ఇద్దరు చిన్న పిల్లలు!"),
      te("ఆ ఆ, కరెక్టే, త్వరగా రండి!"),
      te("హలో? ఎవరైనా ఉన్నారా?"),
    ],
  },
  {
    id: "test-medical",
    name: "06 Medical emergency in the first sentence (Hindi)",
    summary: "The caller's father is unconscious and barely breathing. "
      + "Should: alert an officer on the first turn, ask as little as possible, never tell this caller to "
      + "take a breath, and not invent medical advice when asked what to do.",
    lang: "hi-IN",
    lines: [
      hi("मैडम, मेरे पापा बेहोश हो गए हैं! साँस भी ठीक से नहीं आ रही, और पानी कमर तक है!"),
      hi("सैनिकपुरी, साईनाथ कॉलोनी, घर नंबर तेईस, ग्राउंड फ्लोर।"),
      hi("तीन हैं।"),
      hi("पापा ही हैं, पैंसठ साल के, दिल के मरीज़ हैं।"),
      hi("हाँ सही है, सही है।"),
      hi("पापा को क्या करूँ मैं? कुछ तो बताइए!"),
    ],
  },
  {
    id: "test-water-rises-in-line",
    name: "07 Water rises while waiting (Telugu, then Hindi)",
    summary: "A serious case finishes its questions in Telugu. While the caller waits, her grandson takes the "
      + "phone and says in Hindi that the water has gone from waist to chest. "
      + "Should: add the new details without asking anything, say 'most urgent' once, in Hindi, answer "
      + "'is anyone coming?' honestly, and not repeat 'an officer will speak to you' on every turn.",
    lang: "te-IN",
    lines: [
      te("దెబ్బలేం తగల్లేదండి, కానీ ఇంట్లో నీళ్ళు నడుము దాకా వచ్చేశాయి."),
      te("మూసారాంబాగ్, మూడో వీధి, ఇంటి నంబర్ తొమ్మిది. గ్రౌండ్ ఫ్లోరే."),
      te("ఇద్దరం ఉన్నాం, నేను, మా నాయనమ్మ."),
      te("అవును, కరెక్టే."),
      te("హలో? ఉన్నారా అండి?"),
      hi("मैं इनका पोता बोल रहा हूँ। पानी अब छाती तक आ गया है! दादी से खड़ा नहीं हुआ जा रहा!"),
      hi("कोई आ रहा है या नहीं?"),
      hi("ठीक है।"),
    ],
  },

  // ------------------------------------------------------------------ the caller and the machine
  {
    id: "test-angry",
    name: "08 Angry caller (Telugu)",
    summary: "Swears at the helpline twice but does answer. The area, Prakash Nagar, is not on our list. "
      + "Should: acknowledge the anger once, never say 'calm down', never argue, keep collecting details, "
      + "and read back 'Prakash Nagar', not another Nagar.",
    lang: "te-IN",
    lines: [
      te("మూడు గంటల నుంచి ఫోన్ చేస్తున్నా, ఒక్కరూ ఎత్తరు! పిచ్చి హెల్ప్‌లైన్ ఇది!"),
      te("దెబ్బలేం తగల్లేదు, కానీ ఇంట్లోకి నీళ్ళు వచ్చేశాయి."),
      te("చెవిటివాళ్ళా మీరు? ఎన్ని ప్రశ్నలు అడుగుతారు? బేగంపేట, ప్రకాష్ నగర్, ఇంటి నంబర్ ఆరు, ఫస్ట్ ఫ్లోర్!"),
      te("ఇద్దరం."),
      te("లేరు."),
      te("మోకాళ్ళ దాకా."),
      te("అవును, కరెక్టే."),
    ],
  },
  {
    id: "test-wants-a-person",
    name: "09 Asks for a person, then cooperates (Hindi)",
    summary: "A stable case in Gomti Nagar (not on our list). The caller asks for a person once, then answers everything. "
      + "Should: say an officer will speak when one is free, keep asking so nothing has to be repeated, "
      + "and END the call on the line for an officer, because that is what the caller was told.",
    lang: "hi-IN",
    lines: [
      hi("घर में पानी आ गया है। चोट-वोट किसी को नहीं लगी, पानी भी बढ़ नहीं रहा।"),
      hi("देखिए, मुझे किसी इंसान से बात करनी है।"),
      hi("अच्छा ठीक है। गोमती नगर, विपुल खंड, घर नंबर आठ, फर्स्ट फ्लोर।"),
      hi("दो लोग हैं हम।"),
      hi("नहीं, कोई नहीं।"),
      hi("पैर तक ही है अभी।"),
      hi("हाँ, सही है।"),
      hi("तो अब ऑफिसर से बात होगी?"),
    ],
  },
  {
    id: "test-refuses-machine",
    name: "10 Refuses to talk to a machine (Hindi, then Telugu)",
    summary: "Refuses in the first sentence. While waiting, his wife takes the phone and gives details in Telugu. "
      + "Should: stop asking at once, keep the caller on the line, still write down everything said, "
      + "switch to Telugu, and say 'most urgent' when the breathing trouble is mentioned.",
    lang: "hi-IN",
    lines: [
      hi("मुझे मशीन से बात नहीं करनी, किसी ऑफिसर को फ़ोन दो!"),
      hi("हेलो?"),
      te("సరే వినండి, మేము ముగ్గురం ఉన్నాం, బేగంపేటలో. నీళ్ళు నడుము దాకా వచ్చాయి."),
      te("మా అమ్మకి ఊపిరి ఆడట్లేదు, త్వరగా రండి!"),
      te("బోట్ ఎప్పుడు వస్తుంది?"),
    ],
  },
  {
    id: "test-robot-and-boat",
    name: "11 'Are you a robot?' and 'when will the boat come?' mid-call (Hindi)",
    summary: "Both questions come in the middle of the questions, not while waiting for an officer. "
      + "Should: an honest yes, no time and no promise, no claim that this caller is waiting for an "
      + "officer, then straight back to the question that was open.",
    lang: "hi-IN",
    lines: [
      hi("घर में पानी भर रहा है। चोट किसी को नहीं लगी।"),
      hi("एक मिनट, आप रोबोट हो क्या?"),
      hi("कृष्णलंका, रानीगारी तोटा, घर नंबर चालीस। ग्राउंड फ्लोर।"),
      hi("अच्छा, नाव कब आएगी? कब तक रुकें हम?"),
      hi("चार हैं।"),
      hi("हाँ, एक छोटा बच्चा है, दो साल का।"),
      hi("कमर तक।"),
      hi("हाँ, सही है।"),
    ],
  },

  // ------------------------------------------------------------------ who is calling, and in which language
  {
    id: "test-relative-far-away",
    name: "12 Calling for parents in another city (Hindi)",
    summary: "The caller is not at the flooded house and can't know the floor or the water level. "
      + "Should: never ask 'where are you', 'which floor are you on' or 'including you'; accept "
      + "'I don't know' once and move on; note that a relative reported it.",
    lang: "hi-IN",
    lines: [
      hi("हेलो, मैं बेंगलुरु से बोल रहा हूँ। मेरे मम्मी-पापा हैदराबाद में फँसे हैं, उनका फ़ोन भी बंद हो गया है।"),
      hi("सैनिकपुरी, साईनाथ कॉलोनी, घर नंबर तेईस। पिन कोड पाँच शून्य शून्य शून्य नौ चार।"),
      hi("मैं तो वहाँ हूँ नहीं, फ्लोर का मुझे नहीं पता। घर एक ही मंज़िल का है।"),
      hi("दो लोग हैं वो, दोनों सत्तर से ऊपर के।"),
      hi("मुझे कैसे पता होगा पानी कितना है? आख़िरी बार बोले थे कि बिस्तर तक आ गया।"),
      hi("हाँ, सही है। उनका नंबर भी दे दूँ?"),
    ],
  },
  {
    id: "test-phone-handed-over",
    name: "13 Phone handed to a Telugu neighbour (Hindi, then Telugu)",
    summary: "Starts in Hindi; a neighbour takes the phone and speaks Telugu, then doesn't understand a question. "
      + "Should: switch to Telugu on the neighbour's first sentence, keep everything already said, "
      + "and ask the same question in simpler words (not repeat it, not talk down).",
    lang: "hi-IN",
    lines: [
      hi("घर में बहुत पानी आ गया है! चोट किसी को नहीं लगी, पर पानी तेज़ी से बढ़ रहा है।"),
      hi("सैनिकपुरी, साईनाथ कॉलोनी, घर नंबर तेईस।"),
      te("నేను పక్కింటి వాళ్ళని, ఫోన్ నాకిచ్చారు. వాళ్ళు గ్రౌండ్ ఫ్లోర్‌లోనే ఉన్నారు, పైకి వెళ్ళలేరు."),
      te("నలుగురు ఉన్నారు వాళ్ళు."),
      te("ఆ, వాళ్ళ అమ్మమ్మ ఉంది, ఎనభై ఏళ్ళు."),
      te("అంటే ఏంటి? సరిగ్గా అర్థం కాలేదు."),
      te("అవును, నీళ్ళు నడుము దాకా ఉన్నాయి."),
      te("అవును, అంతా కరెక్టే."),
    ],
  },
  {
    id: "test-switches-twice",
    name: "14 Language changes twice (Hindi, Telugu, Hindi)",
    summary: "The phone goes to a Telugu-speaking friend for two answers and comes back. Later the caller says "
      + "one English word, 'Okay'. "
      + "Should: reply in Telugu to the friend, in Hindi again when the caller returns, keep every "
      + "detail across both changes, and not change language for a single 'Okay'.",
    lang: "hi-IN",
    lines: [
      hi("घर में पानी भर गया है। चोट किसी को नहीं लगी, पर पानी धीरे-धीरे बढ़ रहा है।"),
      hi("कंकड़बाग, रोड नंबर पाँच, घर नंबर सत्रह।"),
      te("నేను వాళ్ళ ఫ్రెండ్‌ని, నాకు హిందీ అంతగా రాదు. వాళ్ళు ఫస్ట్ ఫ్లోర్‌లో ఉన్నారు."),
      te("మొత్తం ఐదుగురు."),
      hi("हाँ, फ़ोन वापस मेरे पास है। मेरी बेटी है, छह महीने की।"),
      hi("Okay."),
      hi("घुटने तक है पानी।"),
      hi("हाँ, सही है।"),
    ],
  },

  // ------------------------------------------------------------------ answers that don't fit
  {
    id: "test-readback-wrong",
    name: "15 The read-back is wrong, again and again (Hindi)",
    summary: "Says 'wrong' with no detail, then corrects the house number, then the number of people, then says "
      + "'wrong' and can't say what. "
      + "Should: ask what is wrong, fix each thing and read the NEW version back, never say the same "
      + "read-back twice, and pass the caller to an officer when they can't say what is wrong.",
    lang: "hi-IN",
    lines: [
      hi("चोट किसी को नहीं लगी, पानी भी बढ़ नहीं रहा।"),
      hi("अन्ना नगर, सेकंड एवेन्यू, घर नंबर बयालीस। ग्राउंड फ्लोर।"),
      hi("तीन।"),
      hi("नहीं, कोई नहीं।"),
      hi("घुटने तक।"),
      hi("नहीं नहीं, गलत है।"),
      hi("घर नंबर बयालीस नहीं, चौबीस है।"),
      hi("नहीं।"),
      hi("लोग तीन नहीं, चार हैं।"),
      hi("नहीं, फिर गलत है।"),
      hi("पता नहीं, बस गलत है।"),
    ],
  },
  {
    id: "test-vague-answers",
    name: "16 Vague answers (Telugu)",
    summary: "No house number ('the blue house behind the station'), 'the upper floor', 'lots of people', "
      + "'ten or twelve', 'a bit below the waist'. "
      + "Should: never invent an exact number or level, ask once more in simpler words, then move on "
      + "and mark the ticket as approximate.",
    lang: "te-IN",
    lines: [
      te("ఇంట్లోకి నీళ్ళు వచ్చేశాయండి. దెబ్బలేం తగల్లేదు."),
      te("బేగంపేట, స్టేషన్ వెనకాల వీధి, నీలం రంగు ఇల్లు."),
      te("పైన ఫ్లోర్‌లో."),
      te("చాలా మంది ఉన్నారండి, బిల్డింగ్ అంతా."),
      te("పది పన్నెండు మంది ఉంటారు."),
      te("ఆ, పిల్లలున్నారు, పెద్దవాళ్ళూ ఉన్నారు."),
      te("నడుము కంటే కొంచెం కింద."),
      te("అవును, కరెక్టే."),
    ],
  },
  {
    id: "test-knows-nothing",
    name: "17 'I don't know' to everything (Hindi)",
    summary: "The caller can't answer anything. "
      + "Should: not loop; after a few tries, give a ticket number and keep the caller on the line for an officer.",
    lang: "hi-IN",
    lines: [
      hi("हेलो? हेलो?"),
      hi("पता नहीं।"),
      hi("पता नहीं, कुछ समझ नहीं आ रहा।"),
      hi("मुझे कुछ नहीं पता!"),
      hi("हेलो?"),
    ],
  },
  {
    id: "test-voice-cracking",
    name: "18 Alone, on a line that breaks up (Hindi)",
    summary: "An old man, alone, on a phone line. Lines 2 to 4 break up more and more, then clear. "
      + "Should: say the line is cutting (not blame the caller), never tell a lone caller to 'give the "
      + "phone to one person', and never guess from broken audio.",
    lang: "hi-IN",
    phone: true,
    lines: [
      hi("बेटा, मैं अकेला हूँ, सत्तर साल का हूँ। घर में पानी भर गया है।"),
      hi("मूसाराम बाग, गली नंबर तीन, घर नंबर नौ।", 1),
      hi("ग्राउंड फ्लोर पर हूँ।", 2),
      hi("हेलो? हेलो? आवाज़ आ रही है?", 3),
      hi("अकेला हूँ, बोला ना! अब सुनाई दे रहा है? पानी कमर तक है।"),
      hi("हाँ, सही है।"),
    ],
  },

  // ------------------------------------------------------------------ not a rescue
  {
    id: "test-relief-only",
    name: "19 Safe, but no food or drinking water (Telugu)",
    summary: "No water in the house and nobody in danger. "
      + "Should: not ask rescue questions that don't apply (the caller already said there is no water), "
      + "not promise a boat, give the ticket number and end.",
    lang: "te-IN",
    lines: [
      te("మేము సేఫ్‌గానే ఉన్నామండి, ఇంట్లో నీళ్ళు లేవు. కానీ రెండు రోజుల నుంచి తాగడానికి నీళ్ళు లేవు, తిండీ లేదు."),
      te("కొండాపూర్, బొటానికల్ గార్డెన్ రోడ్, ఇంటి నంబర్ ఐదు. సెకండ్ ఫ్లోర్."),
      te("నలుగురం."),
      te("లేదండి, అందరూ బాగానే ఉన్నారు."),
      te("ఇంట్లో నీళ్ళు లేవని చెప్పాను కదండి."),
      te("అవును, కరెక్టే."),
    ],
  },
  {
    id: "test-safety-questions",
    name: "20 Live wire, a snake, 'should we leave?' (Hindi, then Telugu)",
    summary: "Three safety questions in the middle of the call; the second and third come in Telugu after the "
      + "caller's wife takes the phone. "
      + "Should: answer each in one sentence, once, in the language it was asked in, then go back to "
      + "the open question; the wire and the snake should reach the ticket's notes.",
    lang: "hi-IN",
    lines: [
      hi("घर में पानी है, चोट किसी को नहीं लगी। पर बिजली का तार टूटकर पानी में गिरा पड़ा है, करंट तो नहीं लगेगा?"),
      hi("बेगमपेट, प्रकाश नगर, घर नंबर छह। ग्राउंड फ्लोर।"),
      te("ముగ్గురం ఉన్నాం. నీళ్ళలో పాము కూడా కనిపించింది!"),
      te("బయటికి వెళ్ళిపోమంటారా, ఇక్కడే ఉండమంటారా?"),
      te("లేరు, ఎవరూ లేరు."),
      te("మోకాళ్ళ దాకా."),
      te("అవును, కరెక్టే."),
    ],
  },
  {
    id: "test-already-rescued",
    name: "21 Already rescued, wants to cancel (Hindi)",
    summary: "The caller was picked up by a boat and wants the earlier request cancelled. Not built yet: today "
      + "the agent asks its usual questions. "
      + "Should: not run the rescue questions, take the ticket number, and mark it for an officer to "
      + "check and close (the agent can't close it on a caller's word).",
    lang: "hi-IN",
    lines: [
      hi("हेलो, हमने सुबह कॉल किया था। अब नाव वालों ने हमें निकाल लिया है, हम सेफ़ हैं। हमारी रिक्वेस्ट कैंसल कर दीजिए।"),
      hi("अरे हमें मदद नहीं चाहिए, बस कैंसल करना है। टिकट नंबर पाँच दो तीन चार था।"),
      hi("अरे सुनिए तो, हम सेफ़ हैं! टीम किसी और के पास भेज दीजिए।"),
    ],
  },
];

/** Hands out a test call's lines in order. again() repeats the last line once (after an error). */
export function lineReader(call) {
  let i = 0, repeated = -1;
  return {
    next: () => call.lines[i++] || null,
    again: () => { if (i > 0 && repeated !== i - 1) { repeated = i - 1; i -= 1; } },
  };
}
