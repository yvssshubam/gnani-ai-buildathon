"""When the LLM call fails, the plainest danger statements are still kept (app/safety_net.py)."""
import pytest

from app import dialogue
from app.dialogue import CallSession
from app.models import Extraction, Ticket
from app.safety_net import danger_by_rule


@pytest.mark.parametrize("text, facts", [
    ("बहुत पानी आ गया है घर में। किसी को चोट नहीं लगी, पर पानी तेज़ी से बढ़ रहा है।", {"injured": False, "water_rising": True}),
    ("कोई घायल नहीं है", {"injured": False}),
    ("मेरे पापा को चोट लगी है", {"injured": True}),
    ("माँ को चोट लगी है, बाकी किसी को चोट नहीं लगी", {"injured": True}),
    ("nobody is hurt but the water is rising fast", {"injured": False, "water_rising": True}),
    ("my brother is badly injured", {"injured": True}),
    ("kisi ko chot nahi lagi, pani badh raha hai", {"injured": False, "water_rising": True}),
    ("ఎవరికీ దెబ్బ తగల్లేదు, కానీ నీళ్ళు వేగంగా పెరుగుతున్నాయి", {"injured": False, "water_rising": True}),
    ("யாருக்கும் அடி படல, ஆனா தண்ணி ஏறிக்கிட்டே இருக்கு", {"injured": False, "water_rising": True}),
])
def test_plain_danger_statements(text, facts):
    assert danger_by_rule(text) == facts


@pytest.mark.parametrize("text", [
    "क्या बकवास है! मुझे किसी इंसान से बात करनी है।",
    "क्या किसी को चोट लगी है?",          # a question, not a statement
    "पानी नहीं बढ़ रहा",                 # not rising
    "Sainikpuri, Sainath Colony, flat number 501",
    "",
])
def test_says_nothing_it_was_not_told(text):
    assert danger_by_rule(text) == {}


class _FailingLLM:
    def extract(self, text, last_question, known):
        return Extraction(unclear=True, llm_failed=True)


class _Store:
    def save(self, t):
        pass


def test_a_failed_llm_call_no_longer_asks_about_injuries_again(monkeypatch):
    monkeypatch.setattr(dialogue, "HUMAN_OPERATORS", 3)
    monkeypatch.setattr(dialogue, "HUMAN_OPERATORS_BUSY", 3)
    s = CallSession(Ticket(id="5301", caller_number="x"), _FailingLLM(), _Store())
    s.greeting()
    r = s.handle("बहुत पानी आ गया है घर में। किसी को चोट नहीं लगी, पर पानी तेज़ी से बढ़ रहा है।", "hi-IN")
    assert s.ticket.danger.injured is False and s.ticket.danger.water_rising is True
    assert r["action"] != "ask:danger" and "चोट" not in r["reply"]


# ---------------------------------------------------------------- people and who is with them

from app.intents import ASK_ROBOT, detect          # noqa: E402
from app.safety_net import facts_by_rule            # noqa: E402


@pytest.mark.parametrize("text, slot, facts", [
    ("మేము నలుగురం ఉన్నాము. వాళ్ళ అమ్మమ్మ కూడా ఉంది, ఆమెకు ఎనభై ఏళ్ళు.", "people", {"people_count": 4, "vulnerable": ["elderly"]}),
    ("हम चार लोग हैं और पानी कमर तक है।", "people", {"people_count": 4}),
    ("पानी घर में भर गया है। मेरी माँ बहुत बीमार है।", "danger", {"vulnerable": ["sick"]}),
    ("we are 4 people, with a baby", "people", {"people_count": 4, "vulnerable": ["infant"]}),
    ("हम चार लोग हैं, बच्चा दो साल का है", "people", {"vulnerable": ["child"]}),   # two numbers: not sure
    ("हम चार लोग हैं", "area", {}),                                               # a count only when asked
    ("कोई बच्चा नहीं है", "vulnerable", {}),
    ("flat number 501, pin code 500094", "people", {}),
])
def test_facts_by_rule(text, slot, facts):
    assert facts_by_rule(text, slot) == facts


@pytest.mark.parametrize("text", ["మీరు robot?", "आप robot हो?", "you are a machine?", "మీరు రోబోటా?"])
def test_robot_questions_in_mixed_language(text):
    assert ASK_ROBOT in detect(text)


def test_robot_word_alone_is_not_a_question():
    assert ASK_ROBOT not in detect("the machine stopped working")
    assert ASK_ROBOT not in detect("मैं मशीन से बात नहीं करूँगा")


class _AlwaysFailing:
    def extract(self, text, last_question, known):
        return Extraction(unclear=True, llm_failed=True)


def test_failed_llm_calls_never_hand_the_caller_over(monkeypatch):
    """Groq failing three times is our problem: the caller must not be handed over as 'stuck'."""
    monkeypatch.setattr(dialogue, "HUMAN_OPERATORS", 3)
    monkeypatch.setattr(dialogue, "HUMAN_OPERATORS_BUSY", 3)
    s = CallSession(Ticket(id="5302", caller_number="x"), _AlwaysFailing(), _Store())
    s.greeting()
    for line in ("हम सैनिकपुरी में रहते हैं", "साईनाथ कॉलोनी के पास", "अंटे एंटी, समझ नहीं आया"):
        r = s.handle(line, "hi-IN")
        assert r["action"] != "handoff"