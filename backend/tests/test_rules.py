"""Unit tests: priority rules, location lookup, language tracking."""
from app.gazetteer import match_locality, resolve
from app.language import LanguageTracker, detect_script_language, reply_language
from app.models import Danger, LocConfidence, Location, Ticket
from app.priority import assess


def make(**kw) -> Ticket:
    return Ticket(id="1234", caller_number="SIM-1", **kw)


# ---------------- priority ----------------
def test_chest_water_is_p0_and_alerts_human():
    p, reasons, alert = assess(make(danger=Danger(water_level="chest")))
    assert p == "P0" and alert and "chest" in reasons[0]


def test_rising_water_with_infant_is_p0():
    p, _, alert = assess(make(vulnerable=["infant"], danger=Danger(water_level="knee", water_rising=True)))
    assert p == "P0" and alert


def test_elderly_is_p1():
    p, _, alert = assess(make(vulnerable=["elderly"], danger=Danger(water_level="knee")))
    assert p == "P1" and not alert


def test_unknown_danger_defaults_to_p1():
    p, reasons, _ = assess(make(needs=["rescue"]))
    assert p == "P1" and "not known" in reasons[-1]


def test_knee_water_no_vulnerable_is_p2():
    p, _, _ = assess(make(needs=["rescue"], danger=Danger(water_level="knee")))
    assert p == "P2"


def test_food_only_is_p3():
    p, _, _ = assess(make(needs=["food", "water"], danger=Danger(water_level="none")))
    assert p == "P3"


# ---------------- location ----------------
def test_tamil_locality_with_suffix():
    assert match_locality("நாங்க வேளச்சேரியில் இருக்கோம்")["name"] == "Velachery"


def test_misspelled_locality():
    assert match_locality("pallikarnai")["name"] == "Pallikaranai"


def test_unknown_place():
    assert match_locality("somewhere near the big tree") is None


def test_confidence_levels():
    assert resolve(Location(locality="Velachery")).confidence == LocConfidence.AREA
    assert resolve(Location(locality="Velachery", street="Bharathi Street")).confidence == LocConfidence.STREET
    assert resolve(Location(locality="Velachery", street="Bharathi Street", door_no="12")).confidence == LocConfidence.EXACT
    assert resolve(Location(street="Bharathi Street")).confidence == LocConfidence.UNKNOWN
    loc = resolve(Location(locality="Tambaram"))
    assert loc.lat and loc.lon


# ---------------- language ----------------
def test_script_detection():
    assert detect_script_language("தண்ணீர் வருது") == "ta-IN"
    assert detect_script_language("పానీ వస్తోంది") == "te-IN"
    assert detect_script_language("पानी आ रहा है") == "hi-IN"
    assert detect_script_language("water is coming") == "en-IN"
    assert detect_script_language("தண்ணீர் first floor வரைக்கும் வந்துருச்சு") == "ta-IN"  # code-mixed
    assert detect_script_language("123 !!") is None


def test_single_english_word_does_not_switch():
    lt = LanguageTracker()
    lt.update("ta-IN", "எங்க வீட்டுல தண்ணீர் வருது")
    assert lt.update("en-IN", "first floor") == "ta-IN"
    assert lt.update("ta-IN", "ஆமா") == "ta-IN"


def test_sustained_change_switches():
    lt = LanguageTracker()
    lt.update("ta-IN", "எங்க வீட்டுல தண்ணீர் வருது")
    lt.update("hi-IN", "मैं पड़ोसी हूँ")
    assert lt.update("hi-IN", "यहाँ चार लोग हैं") == "hi-IN"


def test_short_first_utterance_is_only_tentative():
    lt = LanguageTracker()
    lt.update("en-IN", "help help")
    assert lt.update("ta-IN", "எங்க வீட்டுல தண்ணீர் வருது") == "ta-IN"


def test_unsupported_language_falls_back_to_hindi_with_interpreter():
    assert reply_language("or-IN") == ("hi-IN", True)
    assert reply_language("ta-IN") == ("ta-IN", False)


def test_readback_in_tamil():
    from app.phrases import readback_details
    t = make(people_count=4, vulnerable=["elderly"],
             location=Location(locality="Velachery", street="Gandhi Street", street_native="காந்தி தெரு",
                               door_no="12", floor="first"))
    ta = readback_details(t, "ta-IN")
    assert "வேளச்சேரி" in ta and "காந்தி தெரு" in ta and "4 பேர்" in ta and "முதல் மாடி" in ta
    assert "வயசானவங்க" in ta and "Gandhi" not in ta
    en = readback_details(t, "en-IN")
    assert "Velachery" in en and "Gandhi Street" in en and "first floor" in en


def test_native_street_counts_for_precision():
    loc = resolve(Location(locality="Velachery", street_native="காந்தி தெரு", door_no="12"))
    assert loc.confidence == LocConfidence.EXACT