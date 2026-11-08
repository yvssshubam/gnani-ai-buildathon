"""Off-script turns get a short, checked LLM reply; PIN codes count as location."""
from app import phrases
from app.dialogue import CallSession
from app.gazetteer import clean_pincode
from app.models import Extraction, Ticket


class _Store:
    def save(self, t):
        pass


class _LLM:
    def __init__(self, table):
        self.table, self.questions = table, []

    def extract(self, text, last_question, known):
        self.questions.append(last_question)
        return Extraction(**self.table.get(text, {}))


PIN_OFFER = "pin code తెలుసు, address exact గా తెలియదు, పర్లేదు."


def telugu_call(table):
    s = CallSession(Ticket(id="7101", caller_number="x"), _LLM(table), _Store())
    opening = "నాకు చాలా భయంగా ఉంది. చాలా ఎక్కువ నీళ్ళు వస్తున్నాయి. నాకు చాలా దెబ్బలు తగిలాయి."
    table.setdefault(opening, dict(injured=True, panic="high", spoken_language="te-IN"))
    s.handle(opening, "te-IN")
    return s


def test_i_only_know_the_pin_code_gets_tell_me_the_pin_code():
    """The live call: "I know the pin code, not the exact address, is that ok?" """
    s = telugu_call({PIN_OFFER: dict(dont_know=True, spoken_language="te-IN",
                                     reply="అవును, పిన్ కోడ్ చెప్పండి.")})
    r = s.handle(PIN_OFFER, "te-IN")
    assert r["action"] == "reply" and r["reply"] == "అవును, పిన్ కోడ్ చెప్పండి."
    assert s.last_action.key == "ask:area"                      # still waiting for where they are
    r = s.handle("600042", "te-IN")                              # quick-parsed, no LLM call
    assert s.ticket.location.pincode == "600042"
    assert r["action"] != "ask:area"                             # area answered: on to the next question
    assert s.ticket.location.confidence.value == "area"


def test_the_llm_is_told_what_we_said():
    s = telugu_call({PIN_OFFER: dict(dont_know=True, reply="అవును, పిన్ కోడ్ చెప్పండి."),
                     "ఆరు సున్నా సున్నా సున్నా నాలుగు రెండు": dict(pincode="600042")})
    s.handle(PIN_OFFER, "te-IN")
    s.handle("ఆరు సున్నా సున్నా సున్నా నాలుగు రెండు", "te-IN")
    assert "then the agent said: అవును, పిన్ కోడ్ చెప్పండి." in s.llm.questions[-1]
    assert s.ticket.location.pincode == "600042"


def test_unsafe_or_wrong_language_replies_are_not_spoken():
    for bad in ("Yes, tell me the pin code.",                          # English in a Telugu call
                "అవును, రెస్క్యూ టీమ్ 10 నిమిషాల్లో వస్తారు.",          # a promise and a time
                "అవును " * 20):                                           # too long
        s = telugu_call({PIN_OFFER: dict(dont_know=True, reply=bad)})
        r = s.handle(PIN_OFFER, "te-IN")
        assert r["action"] != "reply", bad
        assert bad.strip() not in r["reply"]


def test_a_normal_answer_never_gets_the_llm_reply():
    s = telugu_call({"వేళచ్చేరి": dict(locality="Velachery", reply="సరే, వేళచ్చేరి.")})
    r = s.handle("వేళచ్చేరి", "te-IN")
    assert r["action"] != "reply"                                # facts changed: the fixed flow continues


def test_llm_replies_cant_keep_a_stuck_caller_from_a_human():
    s = telugu_call({"ఏంటి?": dict(caller_question="other", reply="నెమ్మదిగా చెప్పండి, నేను వింటున్నాను.")})
    actions = [s.handle("ఏంటి?", "te-IN")["action"] for _ in range(5)]
    assert actions.count("reply") <= 3 and "handoff" in actions      # "what?" again and again: a human takes over


def test_at_most_three_llm_replies_a_call():
    lines = [f"line {i}" for i in range(5)]
    s = CallSession(Ticket(id="7102", caller_number="x"),
                    _LLM({**{l: dict(reply="Okay, go on, I am listening.", caller_question="other") for l in lines},
                          "help, nobody hurt": dict(injured=False)}), _Store())
    s.handle("help, nobody hurt", "en-IN")
    actions = []
    for l in lines:
        actions.append(s.handle(l, "en-IN")["action"])
        s.stuck_turns = 0                                              # keep the call going for this check
    assert actions.count("reply") == 3


def test_pin_code_is_read_back_digit_by_digit():
    t = Ticket(id="1", caller_number="x")
    t.location.pincode = "600042"
    assert "6 0 0 0 4 2" in phrases.readback_details(t, "hi-IN")
    assert "పిన్ కోడ్ 6 0 0 0 4 2" in phrases.readback_details(t, "te-IN")


def test_clean_pincode():
    assert clean_pincode("600 042") == "600042"
    assert clean_pincode("६०००४२") == "600042"
    assert clean_pincode("060042") is None and clean_pincode("12345") is None and clean_pincode(None) is None