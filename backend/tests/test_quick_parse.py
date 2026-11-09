"""Short answers are understood without the LLM; the LLM is used at most once per turn."""
from app.dialogue import CallSession
from app.models import Extraction
from app.quick_parse import quick_parse
from app.store import TicketStore


def test_numbers_in_four_languages():
    for text, n in [("4", 4), ("நாலு", 4), ("நாலு பேர்", 4), ("चार लोग", 4), ("నలుగురు", 4), ("three", 3)]:
        assert quick_parse(text, "ask:people").people_count == n, text


def test_two_numbers_goes_to_llm():
    assert quick_parse("நாலு பேர், ஒரு குழந்தை", "ask:people") is None


def test_yes_no_readback():
    for yes in ["ஆமா சரி", "yes correct", "हाँ सही है", "అవును"]:
        assert quick_parse(yes, "readback").confirmation == "yes", yes
    assert quick_parse("இல்ல", "readback").confirmation == "no"
    assert quick_parse("no, third floor", "readback") is None  # correction -> LLM


def test_water_levels():
    assert quick_parse("முட்டி அளவு தண்ணீர்", "ask:water").water_level == "knee"
    assert quick_parse("कमर तक", "ask:water").water_level == "waist"
    assert quick_parse("నడుము వరకు", "ask:water").water_level == "waist"


def test_long_or_unrelated_goes_to_llm():
    assert quick_parse("யாருக்கும் அடிபடல, ஆனா தண்ணீர் ஏறிக்கிட்டே இருக்கு", "ask:danger") is None
    assert quick_parse("4", None) is None  # nothing asked yet


class CountingLLM:
    """Pretends to be the real LLM for the Tamil test call; counts calls."""
    def __init__(self):
        self.calls = 0

    def extract(self, utterance, last_question, known_summary):
        self.calls += 1
        if "வேளச்சேரி" in utterance:
            return Extraction(locality="Velachery", vulnerable=["elderly"], needs=["rescue"], tokens_used=500)
        if "அடிபடல" in utterance:
            return Extraction(injured=False, water_rising=True, tokens_used=500)
        if "காந்தி" in utterance:
            return Extraction(street="Gandhi Street", street_native="காந்தி தெரு", door_no="12", floor="first",
                              tokens_used=500)
        return Extraction(unclear=True, tokens_used=500)

    def phrase(self, *a, **k):
        raise AssertionError("phrase() should not be called any more")


def test_tamil_call_uses_three_llm_calls(tmp_path):
    llm = CountingLLM()
    store = TicketStore(str(tmp_path / "t.db"))
    s = CallSession(store.create("SIM-1"), llm, store)
    s.greeting()
    lines = [
        "எங்க வீட்டுக்குள்ள தண்ணீர் வந்துருச்சு, வேளச்சேரியில இருக்கோம், பாட்டி கூட இருக்காங்க",
        "யாருக்கும் அடிபடல, ஆனா தண்ணீர் ஏறிக்கிட்டே இருக்கு",
        "காந்தி தெரு, கதவு எண் 12, முதல் மாடி",
        "நாலு பேர் இருக்கோம்",
        "முட்டி அளவு தண்ணீர்",
        "ஆமா சரி",
    ]
    r = None
    actions = []
    for line in lines:
        r = s.handle(line, "ta-IN")
        actions.append(r["action"])
    assert actions == ["ask:danger", "ask:street", "ask:people", "ask:water", "readback", "close"], actions
    assert llm.calls == 3          # was 12 (2 per turn) before
    assert r["ticket"]["location"]["confirmed"] is True
    assert r["ticket"]["priority"] == "P0"
    assert "காந்தி தெரு" in s.ticket.transcript[-3].text  # Tamil read-back uses the caller's own words


def test_floor_and_dont_know():
    assert quick_parse("पहली मंज़िल", "ask:floor").floor == "1"
    assert quick_parse("மொட்டை மாடி", "ask:floor").floor == "terrace"
    assert quick_parse("ground floor", "ask:floor").floor == "ground"
    assert quick_parse("తెలియదు", "ask:street").dont_know is True
    assert quick_parse("தெரியல", "ask:area").dont_know is True
    assert quick_parse("पता नहीं", "readback") is None   # at a read-back, "don't know" is not an answer


def test_who_is_vulnerable():
    assert quick_parse("मेरी दादी", "ask:vulnerable_who").vulnerable == ["elderly"]
    assert quick_parse("छोटा बच्चा", "ask:vulnerable_who").vulnerable == ["infant"]
    assert quick_parse("கைக்குழந்தை", "ask:vulnerable_who").vulnerable == ["infant"]
    assert sorted(quick_parse("बच्चे और दादी", "ask:vulnerable_who").vulnerable) == ["child", "elderly"]
    assert quick_parse("గర్భిణీ", "ask:vulnerable_who").vulnerable == ["pregnant"]

import pytest as _pytest   # noqa: E402


@_pytest.mark.parametrize("text", ["అవును, అంతా కరెక్టే.", "అవును, అంతా correctే.", "हाँ, सब सही है।", "yes, all correct"])
def test_all_correct_at_a_readback_is_a_yes(text):
    assert quick_parse(text, "readback").confirmation == "yes"


def test_yes_but_something_wrong_goes_to_the_llm():
    assert quick_parse("हाँ, पर गली गलत है", "readback") is None


@_pytest.mark.parametrize("text, level", [("पानी घुटनों तक है।", "knee"), ("टखनों तक", "ankle"), ("up to my knees", "knee")])
def test_plural_body_parts_for_water(text, level):
    assert quick_parse(text, "ask:water").water_level == level