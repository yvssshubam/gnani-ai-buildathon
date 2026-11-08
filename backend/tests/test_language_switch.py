"""Switching the call's language, and never repeating the same words to a panicked caller."""
from app import phrases
from app.dialogue import CallSession
from app.language import LanguageTracker, reply_language
from app.config import settings
from app.models import Extraction, Ticket


def test_a_full_sentence_in_another_language_switches_at_once():
    lt = LanguageTracker()
    assert lt.update("en-IN", "Please help me, please") == "en-IN"          # 4 words: locks English
    assert lt.update("hi-IN", "पानी घर में आ गया है मुझे बचाओ") == "hi-IN"   # a full Hindi sentence: switch now


def test_short_replies_still_need_two_in_a_row():
    lt = LanguageTracker()
    lt.update("hi-IN", "हमारे घर में पानी भर गया है")
    assert lt.update("en-IN", "ok") == "hi-IN"            # one stray English word: no switch
    assert lt.update("hi-IN", "हाँ") == "hi-IN"            # back to Hindi resets it
    assert lt.update("en-IN", "no") == "hi-IN"
    assert lt.update("en-IN", "yes sir") == "en-IN"       # two short English replies in a row: switch


def test_before_anyone_speaks_the_reply_language_is_the_fallback_not_tamil():
    assert reply_language(None) == (settings.fallback_reply_lang, False)


class _Store:
    def save(self, t):
        pass


class _LLM:
    def __init__(self, table):
        self.table = table

    def extract(self, text, last_question, known):
        return Extraction(**self.table.get(text, {}))


def test_a_panicked_caller_never_hears_the_same_question_twice():
    t = Ticket(id="7001", caller_number="x")
    s = CallSession(t, _LLM({
        "bachao bachao, paani aa gaya": dict(panic="high", needs=["rescue"], injured=False),
        "pata nahi main kahan hoon": dict(dont_know=True),
        "mujhe nahi pata": dict(dont_know=True),
    }), _Store())
    first = s.handle("bachao bachao, paani aa gaya", "hi-IN")
    assert first["action"] == "ask:area"
    second = s.handle("pata nahi main kahan hoon", "hi-IN")
    assert second["action"] == "ask:area"
    assert phrases.say("area3", "hi-IN") in second["reply"]       # the landmark question, new words
    assert phrases.say("area2", "hi-IN") not in second["reply"]


def test_every_language_has_the_new_lines():
    for lang in ("en-IN", "hi-IN", "ta-IN", "te-IN"):
        assert phrases.has("area3", lang) and phrases.has("again", lang)
