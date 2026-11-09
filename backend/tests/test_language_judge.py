"""A wrong language guess from speech-to-text must not take over the call.

The bug: Prisma wrote Hindi speech in Tamil letters and tagged it ta-IN. A 4-word sentence
switched the call to Tamil at once, and from then on everything was Tamil (script and voice).
"""
from app.dialogue import CallSession
from app.language import LanguageTracker, judge_turn, normalize_lang
from app.llm import clean_extraction
from app.models import Extraction, Ticket

HINDI_IN_TAMIL_LETTERS = "பச்சாவோ பச்சாவோ முஜே பச்சாவோ ப்ளீஸ்"   # "bachao bachao mujhe bachao please"
REAL_TAMIL = "எங்க வீட்டுக்குள்ள தண்ணி வந்துடுச்சு காப்பாத்துங்க"


class _Store:
    def save(self, t):
        pass


class _LLM:
    """Says which language each line is, the way the real extractor now does."""
    def __init__(self, langs):
        self.langs = langs

    def extract(self, text, last_question, known):
        return Extraction(spoken_language=self.langs.get(text), panic="low")


def session(langs):
    return CallSession(Ticket(id="9001", caller_number="x"), _LLM(langs), _Store())


# ---------------------------------------------------------------- judge_turn

def test_llm_wins_over_a_wrong_tag_but_is_not_sure():
    assert judge_turn("ta-IN", HINDI_IN_TAMIL_LETTERS, "hi-IN") == ("hi-IN", False)


def test_tag_and_llm_agreeing_is_sure():
    assert judge_turn("ta-IN", REAL_TAMIL, "ta-IN") == ("ta-IN", True)
    assert judge_turn("hi-IN", "हमारे घर में पानी भर गया है", "hi-IN") == ("hi-IN", True)


def test_a_speech_tag_alone_is_never_sure():
    assert judge_turn("ta-IN", HINDI_IN_TAMIL_LETTERS, None) == ("ta-IN", False)


def test_typed_text_is_judged_by_its_letters():
    assert judge_turn(None, "हमारे घर में पानी भर गया है", None) == ("hi-IN", True)


def test_unsure_sentences_need_two_in_a_row():
    lt = LanguageTracker()
    lt.update("en-IN", "please help me now")
    assert lt.update("ta-IN", HINDI_IN_TAMIL_LETTERS, sure=False) == "en-IN"
    assert lt.update("ta-IN", HINDI_IN_TAMIL_LETTERS, sure=False) == "ta-IN"


# ---------------------------------------------------------------- whole calls

def test_hindi_in_tamil_letters_never_turns_the_call_tamil():
    s = session({"Please help me, please": "en-IN", HINDI_IN_TAMIL_LETTERS: "hi-IN"})
    assert s.handle("Please help me, please", "en-IN")["reply_lang"] == "en-IN"
    r1 = s.handle(HINDI_IN_TAMIL_LETTERS, "ta-IN")
    assert r1["reply_lang"] == "en-IN"                 # not sure yet: stays English, never Tamil
    assert r1["lang_check"] == {"stt": "ta-IN", "llm": "hi-IN", "heard": "hi-IN", "sure": False, "call": "en-IN",
                             "llm_failed": False}
    r2 = s.handle(HINDI_IN_TAMIL_LETTERS, "ta-IN")
    assert r2["reply_lang"] == "hi-IN"                 # Hindi twice in a row: switch to Hindi
    callers = [x for x in s.ticket.transcript if x.role == "caller"]
    assert [x.lang for x in callers] == ["en-IN", "hi-IN", "hi-IN"]   # transcript says Hindi, not Tamil


def test_switching_back_and_forth_works_at_once_when_both_agree():
    en, hi = "Please help me, water is everywhere", "हमारे घर में पानी भर गया है"
    en2 = "We are four people on the roof"
    s = session({en: "en-IN", hi: "hi-IN", en2: "en-IN"})
    assert s.handle(en, "en-IN")["reply_lang"] == "en-IN"
    assert s.handle(hi, "hi-IN")["reply_lang"] == "hi-IN"
    assert s.handle(en2, "en-IN")["reply_lang"] == "en-IN"


def test_real_tamil_still_switches_at_once():
    s = session({"Please help me, please": "en-IN", REAL_TAMIL: "ta-IN"})
    s.handle("Please help me, please", "en-IN")
    assert s.handle(REAL_TAMIL, "ta-IN")["reply_lang"] == "ta-IN"


def test_first_sentence_in_tamil_letters_but_hindi_words_starts_the_call_in_hindi():
    s = session({HINDI_IN_TAMIL_LETTERS: "hi-IN"})
    assert s.handle(HINDI_IN_TAMIL_LETTERS, "ta-IN")["reply_lang"] == "hi-IN"


# ---------------------------------------------------------------- LLM output

def test_spoken_language_is_normalised():
    assert clean_extraction({"spoken_language": "Hindi"}).spoken_language == "hi-IN"
    assert clean_extraction({"spoken_language": "te"}).spoken_language == "te-IN"
    assert clean_extraction({"spoken_language": "ta-IN"}).spoken_language == "ta-IN"
    assert clean_extraction({"spoken_language": "klingon"}).spoken_language is None
    assert clean_extraction({}).spoken_language is None
    assert normalize_lang(None) is None


# ---------------------------------------------------------------- short Telugu / Tamil sentences

def test_a_short_telugu_sentence_switches_at_once():
    """The live call: Hindi, then "no, nobody got hurt" in Telugu. 3 words, but a full sentence."""
    lt = LanguageTracker()
    assert lt.update("hi-IN", "Bachaav, bachaav. Bachaao, bachao, bachao!") == "hi-IN"
    assert lt.update("te-IN", "లేదు, ఎవరికీ తగలలేదు.", sure=True) == "te-IN"


def test_stray_english_replies_still_dont_switch():
    for reply in ("ok", "yes sir", "ok thank you", "no no no"):
        lt = LanguageTracker()
        lt.update("hi-IN", "हमारे घर में पानी भर गया है")
        assert lt.update("en-IN", reply, sure=True) == "hi-IN", reply


def test_the_telugu_call_is_answered_in_telugu():
    hi, te = "Bachaav, bachaav. Bachaao, bachao, bachao!", "లేదు, ఎవరికీ తగలలేదు."
    s = session({hi: "hi-IN", te: "te-IN"})
    assert s.handle(hi, "hi-IN")["reply_lang"] == "hi-IN"
    assert s.handle(te, "te-IN")["reply_lang"] == "te-IN"


# ---------------------------------------------------------------- the LLM failed on that turn

class _FailingLLM:
    def extract(self, text, last_question, known):
        return Extraction(unclear=True, llm_failed=True)


def test_if_the_llm_fails_prisma_tag_matching_the_letters_still_switches():
    """The live call: Telugu, then "nobody is hurt" in Hindi while the LLM was unavailable."""
    assert judge_turn("hi-IN", "किसी को भी चोट नहीं लगी है।", None, llm_failed=True) == ("hi-IN", True)
    s = CallSession(Ticket(id="9002", caller_number="x"), _LLM({"నన్ను కాపాడు, నన్ను కాపాడు.": "te-IN"}), _Store())
    assert s.handle("నన్ను కాపాడు, నన్ను కాపాడు.", "te-IN")["reply_lang"] == "te-IN"
    s.llm = _FailingLLM()
    r = s.handle("किसी को भी चोट नहीं लगी है।", "hi-IN")
    assert r["reply_lang"] == "hi-IN" and r["lang_check"]["llm_failed"]


def test_quick_parsed_short_replies_still_need_two_in_a_row():
    assert judge_turn("hi-IN", "नहीं", None) == ("hi-IN", False)


# ---------------------------------------------------------------- a breaking-up line

class _UnclearLLM:
    """Speech-to-text turned a cracking Hindi line into short English words: nothing usable."""
    def extract(self, text, last_question, known):
        if text in ("Hello.", "Can I do?"):
            return Extraction(unclear=True, spoken_language="en-IN")
        return Extraction(spoken_language="hi-IN", injured=False)


def test_misheard_noise_never_switches_the_call_to_english():
    s = CallSession(Ticket(id="5941", caller_number="x"), _UnclearLLM(), _Store())
    s.greeting()
    s.handle("किसी को चोट नहीं लगी है, बस पानी बढ़ रहा है", "hi-IN")
    for heard in ("Hello.", "Can I do?"):
        r = s.handle(heard, "en-IN")
        assert s.ticket.language == "hi-IN"
        assert r["reply_lang"] == "hi-IN"