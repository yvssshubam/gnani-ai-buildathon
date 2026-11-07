"""Acknowledgements, calming, and answers to off-script questions, all from the one extract call."""
from app.dialogue import CallSession, safe_ack
from app.models import Extraction
from app.store import TicketStore


def test_safe_ack_accepts_short_tamil():
    assert safe_ack("பாட்டி கூட இருக்காங்க, புரிஞ்சுது", "ta-IN") == "பாட்டி கூட இருக்காங்க, புரிஞ்சுது."


def test_safe_ack_allows_house_numbers_but_not_times():
    assert safe_ack("गांधी रोड, नंबर 5, ठीक", "hi-IN") == "गांधी रोड, नंबर 5, ठीक।"
    assert safe_ack("5 बजे तक आ जाएंगे", "hi-IN") is None
    assert safe_ack("Help by 6 pm", "en-IN") is None


def test_safe_ack_rejects_promises_times_questions_and_wrong_language():
    assert safe_ack("10 நிமிஷத்துல வந்துடுவாங்க", "ta-IN") is None       # time + promise
    assert safe_ack("Help is coming soon", "en-IN") is None              # promise
    assert safe_ack("எங்க இருக்கீங்க?", "ta-IN") is None                  # question
    assert safe_ack("I understand", "ta-IN") is None                     # wrong language
    assert safe_ack("ठीक है, समझ गया " * 5, "hi-IN") is None              # too long


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def extract(self, *a):
        self.calls += 1
        return self.replies.pop(0)

    def phrase(self, *a, **k):
        raise AssertionError


def session(tmp_path, replies):
    store = TicketStore(str(tmp_path / "t.db"))
    s = CallSession(store.create("SIM-1"), ScriptedLLM(replies), store)
    s.greeting()
    return s


def test_llm_ack_is_used_in_reply(tmp_path):
    s = session(tmp_path, [Extraction(locality="Velachery", vulnerable=["elderly"],
                                      ack="பாட்டி கூட இருக்காங்க, புரிஞ்சுது")])
    r = s.handle("எங்க வீட்டுல தண்ணீர், வேளச்சேரி, பாட்டி கூட இருக்காங்க", "ta-IN")
    assert r["reply"].startswith("பாட்டி கூட இருக்காங்க, புரிஞ்சுது.")
    assert "யாருக்காவது அடிபட்டிருக்கா" in r["reply"]  # then the fixed danger question


def test_bad_ack_falls_back_to_fixed(tmp_path):
    s = session(tmp_path, [Extraction(locality="Velachery", ack="5 நிமிஷத்துல வந்துடுவாங்க")])
    r = s.handle("வேளச்சேரியில மாட்டிக்கிட்டோம், சீக்கிரம் வாங்க", "ta-IN")
    assert r["reply"].startswith("சரி.") and "நிமிஷ" not in r["reply"]


def test_question_gets_fixed_answer_then_flow_continues(tmp_path):
    s = session(tmp_path, [Extraction(locality="Adyar", caller_question="when_help")])
    r = s.handle("அடையாறுல இருக்கோம், படகு எப்ப வரும்?", "ta-IN")
    assert r["reply"].startswith("சரியான நேரம் சொல்ல முடியாது")  # answer first, no "சரி." before it
    assert r["action"] == "ask:danger"


def test_panic_calms_once_and_switches_to_yes_no(tmp_path):
    s = session(tmp_path, [
        Extraction(needs=["rescue"], panic="high"),
        Extraction(injured=False, panic="high"),
    ])
    r1 = s.handle("help help please please water water", "en-IN")
    assert "I am here with you" in r1["reply"]
    assert "Yes or no" in r1["reply"]                    # simple version of the danger question
    r2 = s.handle("no no nobody hurt please hurry", "en-IN")
    assert "I am here with you" not in r2["reply"]       # calming line only once
    assert r2["action"] == "ask:area"


def test_panicked_caller_repeating_same_thing_gets_a_human(tmp_path):
    same = Extraction(needs=["rescue"], panic="high", ack="पानी आ गया, समझ गया")
    s = session(tmp_path, [same.model_copy() for _ in range(6)])
    line = "बचाओ बचाओ, पानी आ गया, जल्दी आओ"
    r1 = s.handle(line, "hi-IN")
    assert "मैं आपके साथ हूँ" in r1["reply"]               # calming line
    assert "हाँ या ना" in r1["reply"]                       # straight to yes/no
    r2 = s.handle(line, "hi-IN")                           # no new info (1) -> same simple question again
    assert r2["action"] == "ask:danger"
    r3 = s.handle(line, "hi-IN")                           # no new info (2) -> human
    assert r3["action"] == "handoff" and r3["done"] is True
    assert "बचाव अधिकारी से जोड़ा जा रहा है" in r3["reply"]
    t = r3["ticket"]
    assert t["call_state"] == "handed_off" and t["status"] == "needs_callback"
    assert t["escalate_to_human"] is True
    assert " ".join(t["id"]) in r3["reply"]               # ticket number still given


def test_calm_caller_gets_three_tries_before_handoff(tmp_path):
    s = session(tmp_path, [Extraction(unclear=True) for _ in range(6)])
    actions = [s.handle("hello hello can you hear", "en-IN")["action"] for _ in range(4)]
    # opening + 3 unanswered questions -> human
    assert actions == ["ask:danger", "ask:danger", "ask:area", "handoff"], actions


def test_no_empty_readback(tmp_path):
    # caller answers only yes/no style things; nothing to read back -> human, not "no details yet. correct?"
    s = session(tmp_path, [Extraction(injured=False), Extraction(unclear=True), Extraction(unclear=True)])
    s.handle("nobody hurt, help", "en-IN")
    replies = [s.handle("I don't know", "en-IN") for _ in range(2)]
    assert all("no details yet" not in r["reply"] for r in replies)


def test_location_given_instead_of_danger_answer(tmp_path):
    """Caller answers 'is anyone hurt?' with their area: keep it, ask danger again, never ask the area again."""
    s = session(tmp_path, [
        Extraction(needs=["rescue"], panic="high", ack="पानी आ गया, समझ गया"),
        Extraction(locality="Tambaram", ack="तांबरम, ठीक"),
        Extraction(injured=False, water_rising=True, ack="ठीक है, पानी बढ़ रहा है"),
    ])
    s.handle("बचाओ बचाओ, पानी आ गया, जल्दी आओ", "hi-IN")
    r2 = s.handle("हम तांबरम में हैं", "hi-IN")
    assert r2["ticket"]["location"]["locality"] == "Tambaram"
    assert r2["action"] == "ask:danger"                       # danger still unanswered -> asked again
    assert "इलाके का नाम" not in r2["reply"]                  # never asks for the area it already has
    r3 = s.handle("कोई घायल नहीं, पानी बढ़ रहा है", "hi-IN")
    assert r3["action"] == "ask:street"                        # next missing part of the address only
    assert "कौन सी गली" in r3["reply"]


def test_dont_know_street_is_an_answer_not_stuck(tmp_path):
    """Panicked caller who doesn't know the street or a landmark is NOT handed off; call continues."""
    s = session(tmp_path, [
        Extraction(locality="Tambaram", needs=["rescue"], panic="high", ack="तांबरम, समझ गया"),
        Extraction(injured=False, water_rising=True, ack="पानी बढ़ रहा है, ठीक"),
    ])
    s.handle("बचाओ, हम तांबरम में हैं, पानी आ गया", "hi-IN")
    r = s.handle("कोई घायल नहीं, पानी बढ़ रहा है", "hi-IN")
    assert r["action"] == "ask:street"
    r = s.handle("पता नहीं", "hi-IN")                  # doesn't know street -> landmark question, no LLM
    assert r["action"] == "ask:street" and r["used_llm"] is False
    assert "मंदिर" in r["reply"]
    r = s.handle("मालूम नहीं", "hi-IN")                # doesn't know a landmark either -> move on
    assert r["action"] in ("ask:floor", "ask:people")
    assert r["done"] is False                          # NOT handed off
    for line in ["पहली मंज़िल", "चार लोग", "नहीं", "कमर तक", "हाँ"]:
        r = s.handle(line, "hi-IN")
        if r["done"]:
            break
    t = r["ticket"]
    assert t["call_state"] == "completed"
    assert t["status"] == "needs_callback"             # area-only -> officer calls back to confirm location
    assert any("area" in f for f in t["followup_reasons"])


def test_yes_to_vulnerable_asks_who(tmp_path):
    s = session(tmp_path, [Extraction(locality="Tambaram", street="Gandhi Road", floor="1", injured=False,
                                      needs=["rescue"], ack="तांबरम, गांधी रोड, ठीक")])
    s.handle("तांबरम, गांधी रोड, पहली मंज़िल, कोई घायल नहीं", "hi-IN")
    r = s.handle("4", "hi-IN")
    assert r["action"] == "ask:vulnerable"
    r = s.handle("हाँ", "hi-IN")
    assert r["action"] == "ask:vulnerable_who" and "कौन है" in r["reply"]
    r = s.handle("मेरी दादी", "hi-IN")
    assert r["ticket"]["vulnerable"] == ["elderly"]
    assert r["action"] == "ask:water"