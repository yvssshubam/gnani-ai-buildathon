/**
 * Scripted callers for simulated calls. Synthetic: no real people, places only from the gazetteer.
 *
 * The caller answers whatever the agent just asked, keyed by the call engine's action
 * ("ask:area", "ask:people", "readback"...). A list is used in order if the same question
 * comes again; the last item repeats. `opening` is said right after the greeting.
 */
export const SCENARIOS = [
  {
    id: "hindi-family",
    name: "Hindi family, read-back correction",
    summary: "Velachery, 4 people with grandmother, waist-deep and rising. Corrects the floor at the read-back.",
    lang: "hi-IN",
    facts: "You are a woman in Velachery, Gandhi Street, house number 12, on the second floor (you first say first floor by mistake). 4 people: you, your husband, your son (10) and your grandmother, who can't walk. Water is waist-deep downstairs and rising. Nobody is hurt. Your phone battery is low.",
    lines: {
      opening: "हमारे घर में पानी भर गया है, हम वेलाचेरी में हैं, किसी को चोट नहीं लगी है",
      "ask:danger": "किसी को चोट नहीं लगी, लेकिन पानी बढ़ रहा है",
      "ask:area": "वेलाचेरी में",
      "ask:street": ["गांधी स्ट्रीट, मकान नंबर बारह, पहली मंज़िल", "पास में बड़ा मंदिर है"],
      "ask:floor": "पहली मंज़िल",
      "ask:people": "हम चार लोग हैं",
      "ask:vulnerable": "हाँ, मेरी दादी साथ में हैं",
      "ask:vulnerable_who": "मेरी दादी, वो चल नहीं पातीं",
      "ask:water": "कमर तक, और बढ़ रहा है",
      readback: ["नहीं, हम दूसरी मंज़िल पर हैं", "हाँ, सही है"],
      ask_correction: "हम दूसरी मंज़िल पर हैं",
      default: "हाँ",
    },
  },
  {
    id: "tamil-urgent",
    name: "Tamil, panicked, chest-deep water",
    summary: "Pallikaranai, 3 people with an elderly woman, water at chest and rising fast.",
    lang: "ta-IN",
    facts: "You are panicking. You are in Pallikaranai, Lake View Road (Eri Karai street), door number 8, ground floor. 3 people: you, your mother and your grandmother. Water is chest-deep and rising fast. A power line is hanging near the gate. Nobody is hurt yet.",
    lines: {
      opening: "ஐயோ காப்பாத்துங்க, வீட்டுக்குள்ள தண்ணீர் நெஞ்சு வரைக்கும் வந்துருச்சு, பாட்டி இருக்காங்க",
      "ask:danger": "யாருக்கும் அடிபடல, ஆனா தண்ணீர் வேகமா ஏறுது",
      "ask:area": "பள்ளிக்கரணை",
      "ask:street": ["ஏரிக்கரை தெரு, கதவு எண் எட்டு", "பக்கத்துல தண்ணீர் தொட்டி இருக்கு"],
      "ask:floor": "தரை தளம்",
      "ask:people": "மூணு பேர்",
      "ask:vulnerable": "ஆமா, பாட்டி இருக்காங்க",
      "ask:vulnerable_who": "பாட்டி, வயசானவங்க",
      "ask:water": "நெஞ்சு வரைக்கும்",
      readback: "ஆமா சரி",
      ask_correction: "எல்லாம் சரிதான்",
      default: "ஆமா",
    },
  },
  {
    id: "english-area-only",
    name: "English, doesn't know the street",
    summary: "Madipakkam, 2 people, knee-deep. Can only name the area and a landmark.",
    lang: "en-IN",
    facts: "You and your wife just moved to Madipakkam and don't know the street name. There is a big school near your house. Ground floor, water is knee-deep. Nobody is hurt. Your wife needs her diabetes medicine.",
    lines: {
      opening: "Hello, water has come into our house. We are in Madipakkam.",
      "ask:danger": "No one is hurt.",
      "ask:area": "Madipakkam.",
      "ask:street": ["I don't know the street name, we just moved here.", "There is a big school near our house."],
      "ask:floor": "Ground floor.",
      "ask:people": "Two of us.",
      "ask:vulnerable": "No.",
      "ask:vulnerable_who": "No one.",
      "ask:water": "Up to the knee.",
      readback: "Yes, that's right.",
      ask_correction: "Everything is right.",
      default: "Yes.",
    },
  },
];

/** A script reader that remembers which answers it has used. */
export function scriptReader(scenario) {
  const used = {};
  return (actionKey) => {
    const key = actionKey && scenario.lines[actionKey] != null ? actionKey : "default";
    const v = scenario.lines[key];
    if (!Array.isArray(v)) return v;
    const i = used[key] || 0;
    used[key] = i + 1;
    return v[Math.min(i, v.length - 1)];
  };
}
