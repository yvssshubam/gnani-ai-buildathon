/**
 * Your test calls, as simulated callers on the call screen. Unlike the other simulated callers,
 * these say their lines in order (like backend/my_calls/*.txt), keep talking while the call is in
 * line for an officer, and can break up (crack 1-3) like a bad phone line.
 */

const hi = (text, crack) => ({ lang: "hi-IN", text, crack });
const te = (text, crack) => ({ lang: "te-IN", text, crack });

export const TEST_CALLS = [
  {
    id: "test-full-call",
    name: "Test call 1: full call, start to finish",
    summary: "Hindi caller, angry, wants a person, offers the address, PIN code, hands the phone to a Telugu "
      + "neighbour, asks what a question means, then asks about the boat and whether it's a robot while in line.",
    lang: "hi-IN",
    lines: [
      hi("बहुत पानी आ गया है घर में, किसी को चोट नहीं लगी, पर पानी तेज़ी से बढ़ रहा है।"),
      hi("क्या बकवास है, मुझे किसी इंसान से बात करनी है!"),
      hi("एरिया का नाम नहीं पता, पर घर का पता मालूम है, बता दूँ?"),
      hi("Sainikpuri, Sainath Colony, house number 23, pin code 500094."),
      te("నేను పక్కింటి వాళ్ళని, ఫోన్ నాకు ఇచ్చారు. వాళ్ళు గ్రౌండ్ ఫ్లోర్‌లోనే ఉన్నారు, పైకి వెళ్ళలేరు."),
      te("మేము నలుగురం ఉన్నాము. వాళ్ళ అమ్మమ్మ కూడా ఉంది, ఆమెకి ఎనభై ఏళ్ళు."),
      te("అంటే ఏంటి? సరిగ్గా అర్థం కాలేదు."),
      te("అవును, నీళ్ళు నడుము వరకు ఉన్నాయి."),
      te("అవును, అంతా కరెక్టే."),
      te("boat ఎప్పుడు వస్తుంది?"),
      te("మీరు రోబోటా?"),
      te("సరే."),
    ],
  },
  {
    id: "test-voice-cracking",
    name: "Test call 2: the caller's voice cracks",
    summary: "Hindi caller on a phone line. Lines 3 to 5 break up more and more, then the caller moves and is "
      + "clear again. The agent should ask again, then ask for one person close to the phone, and never guess.",
    lang: "hi-IN",
    phone: true,
    lines: [
      hi("पानी घर में भर गया है, मेरी माँ बहुत बीमार है।"),
      hi("हम वेलाचेरी में हैं, गांधी स्ट्रीट, घर नंबर बारह, ग्राउंड फ्लोर।"),
      hi("किसी को चोट नहीं लगी है।", 1),
      hi("हम चार लोग हैं।", 2),
      hi("हेलो? हेलो? सुनाई दे रहा है?", 3),
      hi("हाँ, अब ठीक है, मैं खिड़की के पास आ गया। हम चार लोग हैं, और पानी कमर तक है।"),
      hi("हाँ, सब सही है।"),
    ],
  },
  {
    id: "test-ideal-call",
    name: "Test call 3: the ideal call",
    summary: "Hindi caller who answers every question clearly, first time: nobody hurt, full address, "
      + "ground floor, three adults, knee-deep water. Read-back, ticket number, call ends.",
    lang: "hi-IN",
    lines: [
      hi("नहीं, किसी को चोट नहीं लगी है, और पानी अभी बढ़ नहीं रहा।"),
      hi("अन्ना नगर, सेकंड एवेन्यू, घर नंबर बयालीस।"),
      hi("ग्राउंड फ्लोर।"),
      hi("हम तीन लोग हैं।"),
      hi("नहीं, सब बड़े हैं, कोई बीमार नहीं है।"),
      hi("पानी घुटनों तक है।"),
      hi("हाँ, सब सही है।"),
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