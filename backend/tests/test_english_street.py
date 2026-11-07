from app.dialogue import apply_extraction
from app.gazetteer import resolve, to_english_letters
from app.models import Extraction, LocConfidence, Location, Ticket


def _ticket(**kw):
    return Ticket(id="1", caller_number="x", **kw)


def test_known_words_in_three_scripts():
    assert to_english_letters("नेहरू स्ट्रीट") == "Nehru Street"
    assert to_english_letters("गांधी रोड") == "Gandhi Road"
    assert to_english_letters("காந்தி தெரு") == "Gandhi Street"
    assert to_english_letters("గాంధీ వీధి") == "Gandhi Street"


def test_transliteration_library_installed():
    import importlib.util
    assert importlib.util.find_spec("indic_transliteration"), \
        "run: python -m pip install indic-transliteration  (street names stay in the caller's script without it)"


def test_unknown_name_still_comes_out_in_english_letters():
    out = to_english_letters("शिवाजी गली")
    assert out.isascii() and out.endswith("Street")


def test_english_text_untouched():
    assert to_english_letters("Nehru Street") == "Nehru Street"
    assert to_english_letters("12") == "12"


def test_hindi_native_only_street_becomes_english():
    # the exact ticket from the Hindi run
    loc = resolve(Location(locality="Velachery", street_native="नेहरू स्ट्रीट", door_no="12", floor="second"))
    assert loc.street == "Nehru Street"
    assert loc.street_native == "नेहरू स्ट्रीट"   # kept for the read-back
    assert loc.confidence == LocConfidence.EXACT


def test_native_text_in_english_field_is_converted():
    loc = resolve(Location(locality="Velachery", street="नेहरू स्ट्रीट"))
    assert loc.street == "Nehru Street"


def test_native_only_answer_in_a_later_turn_is_used():
    t = _ticket()
    apply_extraction(t, Extraction(locality="Velachery"))
    apply_extraction(t, Extraction(street_native="नेहरू स्ट्रीट"))   # nothing else in this turn
    assert t.location.street == "Nehru Street"
    assert t.location.confidence == LocConfidence.STREET


def test_corrected_native_street_replaces_old_one():
    t = _ticket()
    apply_extraction(t, Extraction(locality="Velachery", street_native="नेहरू स्ट्रीट"))
    apply_extraction(t, Extraction(street_native="गांधी रोड"))
    assert t.location.street == "Gandhi Road"


def test_tamil_landmark_still_finds_locality():
    loc = resolve(Location(landmark_native="வேளச்சேரி கோவில்"))
    assert loc.locality == "Velachery" and loc.landmark.isascii()


def _finish(t):
    from app.dialogue import CallSession
    s = CallSession.__new__(CallSession)
    s.ticket = t
    s._finish()
    return t


def test_p2_with_water_gets_a_recheck():
    from app.dialogue import RECHECK_REASON
    t = _ticket(location=Location(locality="Velachery", street="Nehru Street", door_no="12",
                                 confidence=LocConfidence.EXACT, confirmed=True))
    t.priority, t.danger.water_level = "P2", "knee"
    assert RECHECK_REASON in _finish(t).followup_reasons


def test_p3_without_water_gets_no_recheck():
    from app.dialogue import RECHECK_REASON
    t = _ticket(location=Location(confidence=LocConfidence.EXACT, confirmed=True))
    t.priority = "P3"
    assert RECHECK_REASON not in _finish(t).followup_reasons


def test_locality_in_hindi_and_telugu_script():
    from app.gazetteer import match_locality
    cases = {"वेलाचेरी में": "Velachery", "तांबरम में हैं": "Tambaram", "अन्ना नगर": "Anna Nagar",
             "వేళచ్చేరిలో": "Velachery", "తాంబరంలో": "Tambaram", "క్రోంపేట": "Chromepet"}
    for said, name in cases.items():
        assert (match_locality(said) or {}).get("name") == name, said


def test_non_places_do_not_match_a_locality():
    from app.gazetteer import match_locality
    for said in ("पानी आ गया", "मुंबई", "चेन्नई"):
        assert match_locality(said) is None, said


def test_mixed_script_hinglish_street():
    assert to_english_letters("नेहरू street") == "Nehru street"
    assert to_english_letters("Nehru स्ट्रीट") == "Nehru Street"


def test_english_words_written_in_devanagari():
    assert to_english_letters("लेक व्यू रोड") == "Lake View Road"
    assert to_english_letters("चर्च स्ट्रीट") == "Church Street"
    assert to_english_letters("फर्स्ट क्रॉस स्ट्रीट") == "First Cross Street"
    assert to_english_letters("बस स्टॉप").isascii()


def test_extractor_is_told_the_call_language():
    from app.dialogue import known_summary
    t = _ticket(location=Location(locality="Madipakkam"))
    assert "call language: Hindi, Devanagari script" in known_summary(t, "hi-IN")
    assert "Madipakkam" in known_summary(t, "hi-IN")
    assert "call language" not in known_summary(t)        # old call style still works


# ---- answers to a read-back
def _session_after_readback(kind="readback"):
    from app.dialogue import Action, CallSession
    s = CallSession.__new__(CallSession)
    s.ticket = _ticket(location=Location(locality="Madipakkam", street="Church Road", door_no="14",
                                         confidence=LocConfidence.EXACT))
    s.ticket.people_count = 5
    s.last_action = Action(kind)
    s.readbacks = 1
    s.facts_changed = False
    return s


def test_no_without_new_details_asks_what_is_wrong():
    s = _session_after_readback()
    # "nahi galat he": the LLM may flag both "no" and "correction", but nothing changed
    assert s._next_action(Extraction(confirmation="no", correction=True)).kind == "ask_correction"
    assert s._next_action(Extraction(confirmation="no")).kind == "ask_correction"


def test_correction_with_new_details_reads_back_again():
    s = _session_after_readback()
    s.facts_changed = True               # e.g. "nahi, second floor"
    assert s._next_action(Extraction(confirmation="no", correction=True)).kind == "readback"


def test_second_no_after_asking_what_is_wrong_does_not_loop():
    s = _session_after_readback("ask_correction")
    assert s._next_action(Extraction(confirmation="no")).kind in ("readback", "close")


def test_yes_closes():
    s = _session_after_readback()
    assert s._next_action(Extraction(confirmation="yes")).kind == "close"