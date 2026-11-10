"""The line review of 10 Nov: things callers heard that were wrong, cold or untrue, and the fixes."""
import pytest

from app import phrases, prompts
from app.dialogue import CallSession, WRONG_DETAILS_REASON
from app.gazetteer import match_locality
from app.models import Extraction, Ticket


class _Store:
    def save(self, t):
        pass


class _LLM:
    """Returns the facts listed for each caller line; anything else has nothing usable in it."""
    def __init__(self, table):
        self.table = table

    def extract(self, text, last_question, known):
        return Extraction(**self.table.get(text, {}))

    def phrase(self, instruction, lang, utterance, fallback_text):
        return fallback_text


def call(table):
    return CallSession(Ticket(id="7301", caller_number="SIM-1"), _LLM(table), _Store())


# ---------------------------------------------------------------- the wrong area on the ticket

@pytest.mark.parametrize("said", [
    "Rajendra Nagar", "Gandhi Nagar", "Indira Nagar", "Gomti Nagar", "Ram Nagar", "Vasant Nagar",
    "राजेंद्र नगर", "शांति नगर", "గాంధీ నగర్", "Manalipuram", "Annapurna Nagar"])
def test_an_area_we_dont_know_is_not_turned_into_one_we_do(said):
    """Any "... Nagar" used to be saved, and read back, as "T. Nagar"."""
    assert match_locality(said) is None, said


@pytest.mark.parametrize("said,name", [
    ("T Nagar", "T. Nagar"), ("T.Nagar", "T. Nagar"), ("we are in t nagar", "T. Nagar"), ("टी नगर", "T. Nagar"),
    ("KK Nagar", "K.K. Nagar"), ("Anna Nagar", "Anna Nagar"), ("anna nagr", "Anna Nagar"),
    ("velacheri", "Velachery"), ("vela cheri", "Velachery"), ("Tambram", "Tambaram"), ("తాంబరంలో", "Tambaram")])
def test_known_areas_still_match_with_spelling_slips(said, name):
    assert (match_locality(said) or {}).get("name") == name, said


# ---------------------------------------------------------------- "I want to talk to a person"

def test_a_stable_caller_who_asked_for_a_person_ends_in_line_for_one():
    """They were told an officer will speak to them. The call used to end without one."""
    s = call({
        "water came in, nobody is hurt, it is not rising": dict(injured=False, water_rising=False, needs=["rescue"]),
        "I want to talk to a real person": dict(asks_for_human=True),
        "Velachery, Gandhi Street, door 12, first floor": dict(locality="Velachery", street="Gandhi Street",
                                                               door_no="12", floor="first"),
        "ankle": dict(water_level="ankle"),
    })
    s.greeting()
    s.handle("water came in, nobody is hurt, it is not rising", "en-IN")
    r = s.handle("I want to talk to a real person", "en-IN")
    assert "an officer will speak to you when one is free" in r["reply"]
    s.handle("Velachery, Gandhi Street, door 12, first floor", "en-IN")
    s.handle("2", "en-IN")
    s.handle("no", "en-IN")
    s.handle("ankle", "en-IN")
    r = s.handle("yes", "en-IN")
    assert s.ticket.priority == "P2"                      # asking for a person doesn't make it urgent
    assert r["waiting"] is True and r["done"] is False    # ...but they do stay on the line for one
    assert "An officer will speak to you" in r["reply"] and "most urgent" not in r["reply"]


# ---------------------------------------------------------------- the read-back

def test_the_same_read_back_is_never_said_twice():
    s = call({
        "nobody hurt, not rising, Anna Nagar, Second Avenue, door 42, ground floor, 3 people, knee deep": dict(
            injured=False, water_rising=False, locality="Anna Nagar", street="Second Avenue", door_no="42",
            floor="ground", people_count=3, water_level="knee"),
        "no, that is wrong": dict(confirmation="no"),
        "still wrong": dict(confirmation="no"),
    })
    s.greeting()
    s.handle("nobody hurt, not rising, Anna Nagar, Second Avenue, door 42, ground floor, 3 people, knee deep", "en-IN")
    first = s.handle("no", "en-IN")                       # nobody vulnerable -> the read-back
    assert first["action"] == "readback"
    assert s.handle("no, that is wrong", "en-IN")["action"] == "ask_correction"
    r = s.handle("still wrong", "en-IN")
    assert r["action"] == "handoff" and r["waiting"] is True
    assert r["reply"] != first["reply"]
    assert WRONG_DETAILS_REASON in s.ticket.followup_reasons


# ---------------------------------------------------------------- panic

def test_no_bare_okay_to_a_caller_who_fears_for_their_life():
    s = call({"help, we are going to die": dict(needs=["rescue"], panic="high"),
              "we are going to die": dict(panic="high")})
    s.greeting()
    s.handle("help, we are going to die", "en-IN")
    r = s.handle("we are going to die", "en-IN")
    assert not r["reply"].startswith("Okay.")


def test_urgent_and_calming_lines_are_not_piled_on_one_turn():
    """Father unconscious: "most urgent, an officer is being alerted" is the reassurance. The
    calming line waits for the next question, and never says "take a breath"."""
    s = call({"my father is unconscious": dict(medical_emergency=True, injured=True, panic="high", needs=["rescue"]),
              "Anna Nagar, Second Avenue, door 42, ground floor": dict(locality="Anna Nagar", street="Second Avenue",
                                                                       door_no="42", floor="ground")})
    s.greeting()
    r1 = s.handle("my father is unconscious", "en-IN")
    assert "most urgent" in r1["reply"] and "I am right here" not in r1["reply"]
    r2 = s.handle("Anna Nagar, Second Avenue, door 42, ground floor", "en-IN")
    assert "I am right here" in r2["reply"]
    assert "breath" not in phrases.say("calm", "en-IN") and "साँस" not in phrases.say("calm", "hi-IN")


# ---------------------------------------------------------------- what the lines promise and assume

CALLBACK_WORDS = ["call you back", "call this number", "कॉल करेंगे", "कॉल करेंगी", "కాల్ చేస్తాం", "కాల్ చేస్తారు",
                  "கூப்பிடுவோம்", "கூப்பிடுவாங்க"]


def test_no_line_promises_a_callback():
    """Callbacks are flagged on the ticket for an operator; the agent can't promise one."""
    for lang, lines in phrases.PHRASES.items():
        for key, text in lines.items():
            assert not any(w in text for w in CALLBACK_WORDS), (lang, key)


def test_questions_work_for_someone_calling_about_another_house():
    """A son calling from another city was asked "where are YOU", "which floor are YOU on" and
    "how many people including YOU"."""
    en, hi = phrases.PHRASES["en-IN"], phrases.PHRASES["hi-IN"]
    for key in ("area1", "floor1", "people1", "people2"):
        assert "you" not in en[key].lower().replace("your", ""), key
        assert "आप " not in hi[key] and "आपको" not in hi[key], key


def test_the_greeting_says_flood_helpline():
    assert prompts.GREETING["text"].startswith("फ़्लड हेल्पलाइन")


# ---------------------------------------------------------------- sounding like a person

def _ideal(lang="hi-IN"):
    s = call({
        "nobody hurt, not rising": dict(injured=False, water_rising=False, ack="किसी को चोट नहीं, ठीक है"),
        "Anna Nagar, Second Avenue, door 42": dict(locality="Anna Nagar", street="Second Avenue", door_no="42",
                                                   ack="अन्ना नगर, समझ गई"),
        "all adults, nobody sick": dict(ack="कोई बीमार नहीं, ठीक है"),
        "knee": dict(water_level="knee", ack="घुटने तक पानी, समझ गई"),
    })
    s.greeting()
    replies = [s.handle(text, lang)["reply"] for text in (
        "nobody hurt, not rising", "Anna Nagar, Second Avenue, door 42", "ग्राउंड फ्लोर", "3",
        "all adults, nobody sick", "knee")]
    return s, replies


def test_relief_is_said_once_when_nobody_is_hurt():
    _, replies = _ideal()
    assert replies[0].startswith("शुक्र है, सब ठीक हैं।")
    assert sum("शुक्र है" in r for r in replies) == 1


def test_relief_is_not_said_when_the_case_is_worrying():
    for facts in (dict(injured=False, water_rising=True), dict(injured=False, water_level="chest"),
                  dict(injured=False, trapped=True), dict(injured=False, vulnerable=["elderly"]),
                  dict(injured=False, panic="high")):
        s = call({"x": facts})
        s.greeting()
        assert "शुक्र है" not in s.handle("x", "hi-IN")["reply"], facts


def test_a_detail_is_repeated_back_only_for_an_address_or_a_number():
    _, replies = _ideal()
    assert replies[1].startswith("अन्ना नगर, समझ गई।")          # an address: worth confirming
    assert "कोई बीमार नहीं" not in replies[4]                   # a plain answer: not parroted
    assert "घुटने तक पानी" not in replies[5]


def test_plain_answers_get_a_different_word_each_time():
    _, replies = _ideal()
    starts = [r.split("।")[0] for r in (replies[2], replies[3], replies[4])]
    assert starts == ["ठीक है", "समझ गई", "हाँ, लिख लिया"], starts


def test_read_back_goes_from_the_area_down_to_the_house():
    s, replies = _ideal()
    assert replies[5].endswith("एक बार दोहरा देती हूँ। 3 लोग हैं, Anna Nagar, Second Avenue, घर नंबर 42, ग्राउंड फ्लोर पर। क्या ये सही है?")
    s.ticket.language = "en-IN"
    assert phrases.readback_details(s.ticket, "en-IN") == "3 people, at door number 42, Second Avenue, Anna Nagar, ground floor"


def test_every_language_has_the_same_lines():
    keys = set(phrases.PHRASES["en-IN"])
    for lang, lines in phrases.PHRASES.items():
        assert set(lines) == keys, lang
