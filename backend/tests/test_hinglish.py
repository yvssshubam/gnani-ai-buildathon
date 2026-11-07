"""Hindi / Tamil / Telugu typed in English letters (Hinglish, Tanglish), e.g. by SMS."""
import pytest

from app.language import LanguageTracker, detect_script_language
from app.quick_parse import quick_parse


@pytest.mark.parametrize("text, lang", [
    ("hamare ghar mein paani bhar gaya hai", "hi-IN"),
    ("hum velachery mein hain", "hi-IN"),
    ("nahi galat he", "hi-IN"),
    ("haan sahi hai", "hi-IN"),
    ("nahi", "hi-IN"),
    ("naanga velachery la irukom", "ta-IN"),
    ("thanni romba irukku", "ta-IN"),
    ("memu velachery lo unnam", "te-IN"),
    # plain English must stay English
    ("Church Road, house number 14, first floor", "en-IN"),
    ("he is not injured", "en-IN"),
    ("main road", "en-IN"),
    ("Hi", "en-IN"),
    ("we are 5 people", "en-IN"),
    ("yes", "en-IN"),
])
def test_roman_language_detection(text, lang):
    assert detect_script_language(text) == lang


def test_native_script_still_wins():
    assert detect_script_language("हम Madipakkam में हैं") == "hi-IN"
    assert detect_script_language("முட்டி அளவு தண்ணீர்") == "ta-IN"


def test_hinglish_call_stays_hindi():
    tr = LanguageTracker()
    tr.update(detect_script_language("हमारे घर में पानी आ गया है"), "हमारे घर में पानी आ गया है")
    for line in ("nahi galat he", "nahi, second floor hai", "haan sahi hai"):
        lang = tr.update(detect_script_language(line), line)
    assert lang == "hi-IN"


def _q(text, key):
    return quick_parse(text, key)


def test_readback_pure_yes_and_no():
    assert _q("haan sahi hai", "readback").confirmation == "yes"
    assert _q("हाँ सही है", "readback").confirmation == "yes"
    assert _q("nahi galat he", "readback").confirmation == "no"


def test_readback_yes_with_a_correction_goes_to_the_llm():
    assert _q("haan, second floor", "readback") is None
    assert _q("हाँ, दूसरी मंज़िल", "readback") is None


def test_roman_short_answers():
    assert _q("do log hain", "ask:people").people_count == 2
    assert _q("naalu per", "ask:people").people_count == 4
    assert _q("paani kamar tak hai", "ask:water").water_level == "waist"
    assert _q("ghutne tak", "ask:water").water_level == "knee"
    assert _q("dusri manzil", "ask:floor").floor == "2"
    assert _q("meri dadi", "ask:vulnerable_who").vulnerable == ["elderly"]
    assert _q("ek chhota baccha", "ask:vulnerable_who").vulnerable == ["infant"]
    assert _q("pata nahi", "ask:street").dont_know is True
    assert _q("koi nahi", "ask:danger").injured is False


def test_english_letter_words_match_whole_words_only():
    # Tamil "illa" (no) used to become "sick" because "ill" is inside it
    e = _q("illa", "ask:vulnerable_who")
    assert e is None or "sick" not in e.vulnerable
    # "meda" (Telugu: neck) must not fire inside the locality Medavakkam
    e = _q("Medavakkam", "ask:water")
    assert e is None or e.water_level != "neck"


def test_native_script_answers_unchanged():
    assert _q("நாலு", "ask:people").people_count == 4
    assert _q("முட்டி அளவு தண்ணீர்", "ask:water").water_level == "knee"