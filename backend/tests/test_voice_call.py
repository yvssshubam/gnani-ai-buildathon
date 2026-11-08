"""Voice endpoints end to end, with Gnani and the LLM faked (no network, no credits)."""
import pytest
from fastapi.testclient import TestClient

from app import main, phrases
from app.models import Extraction
from app.voice.call import fixed_lines, keyterms
from app.voice.gnani_http import GnaniError
from app.voice.stt import Transcript
from app.voice.tts import TimbreTTS

WAV = b"RIFF" + b"\0" * 60


class FakeSTT:
    """Returns the text/language queued for each clip; records the context it was given."""
    def __init__(self):
        self.queue, self.contexts, self.hints = [], [], []

    async def transcribe(self, audio, *, filename="turn.wav", previous_text=None, **kw):
        self.contexts.append(previous_text)
        self.hints.append(kw)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        text, lang = item
        return Transcript(text=text, language=lang, seconds=0.2)


class FakeLLM:
    def extract(self, text, last_question, known):
        return Extraction(locality="Velachery", injured=False, ack="ठीक है")


@pytest.fixture
def api(tmp_path, monkeypatch):
    tts = TimbreTTS(client=None, api_key="k", voices={"hi-IN": "Yashvi", "en-IN": "Shlok", "ta-IN": "Trisha"},
                    fallback_lang="hi-IN", cache_dir=str(tmp_path / "cache"))
    spoken = []

    async def fake_synth(text, lang):  # writes the cache file like the real one, no HTTP
        spoken.append((text, lang))
        tts.cached_path(text, lang).write_bytes(WAV)
        return WAV
    monkeypatch.setattr(tts, "synthesize", fake_synth)
    monkeypatch.setattr(main.settings, "tts_cache_dir", str(tmp_path / "cache"))
    stt = FakeSTT()
    monkeypatch.setitem(main.voice, "stt", stt)
    monkeypatch.setitem(main.voice, "tts", tts)
    monkeypatch.setattr(main, "llm", FakeLLM())
    client = TestClient(main.app)
    client.stt, client.spoken = stt, spoken
    return client


def start(api):
    r = api.post("/api/voice/calls", json={})
    assert r.status_code == 200, r.text
    return r.json()


def test_start_speaks_the_greeting(api):
    call = start(api)
    assert call["greeting"] and len(call["audio"]) == 1
    audio = api.get(call["audio"][0])
    assert audio.status_code == 200 and audio.content == WAV


def test_turn_runs_the_dialogue_and_speaks_each_part(api):
    call = start(api)
    api.stt.queue.append(("हम वेलाचेरी में हैं, कोई घायल नहीं", "hi-IN"))
    r = api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"audio")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["heard"] == "हम वेलाचेरी में हैं, कोई घायल नहीं" and res["heard_lang"] == "hi-IN"
    assert res["reply_lang"] == "hi-IN" and res["reply"]
    assert " ".join(res["reply_parts"]) == res["reply"]
    assert len(res["audio"]) == len(res["reply_parts"]) and all(res["audio"])
    assert res["ticket"]["location"]["locality"] == "Velachery"
    # the greeting is NOT sent as context: it would push the first transcription toward its language
    assert api.stt.contexts[0] is None


def test_next_turn_gets_the_agent_question_in_english_as_context(api):
    call = start(api)
    api.stt.queue += [("हम वेलाचेरी में हैं", "hi-IN"), ("चार लोग", "hi-IN")]
    first = api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"a").json()
    asked_en = main.sessions[call["call_id"]].question_en()
    api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"b")
    assert first["reply_lang"] == "hi-IN"
    # the same question, but in English: context that doesn't push Prisma toward one script
    assert api.stt.contexts[1] == asked_en and asked_en.isascii()


def test_stt_context_can_be_turned_off(api, monkeypatch):
    monkeypatch.setattr(main.settings, "stt_context", "none")
    call = start(api)
    api.stt.queue += [("हम वेलाचेरी में हैं", "hi-IN"), ("चार लोग", "hi-IN")]
    api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"a")
    api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"b")
    assert api.stt.contexts == [None, None]


def test_silence_asks_again_without_using_a_turn(api):
    call = start(api)
    api.stt.queue.append(("", None))
    res = api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"rain").json()
    assert res["action"] == "not_heard" and not res["done"]
    assert res["reply"] == phrases.say("not_heard", res["reply_lang"])
    assert main.sessions[call["call_id"]].turns == 0


def test_stt_failure_is_502_and_the_call_survives(api):
    call = start(api)
    api.stt.queue += [GnaniError("STT", 504, "UPSTREAM_TIMEOUT", ""), ("हम वेलाचेरी में हैं", "hi-IN")]
    assert api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"a").status_code == 502
    assert api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"a").status_code == 200


def test_tts_failure_still_returns_the_text(api, monkeypatch):
    call = start(api)
    tts = main.voice["tts"]

    async def broken(text, lang):
        raise GnaniError("TTS", 402, "", "no credit")
    monkeypatch.setattr(tts, "synthesize", broken)
    api.stt.queue.append(("हम वेलाचेरी में हैं", "hi-IN"))
    res = api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"a").json()
    assert res["reply"] and res["audio"] and not any(res["audio"]) and "402" in res["tts_error"]


def test_bad_requests(api):
    call = start(api)
    assert api.post("/api/voice/calls/nope/turn", content=b"a").status_code == 404
    assert api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"").status_code == 400
    assert api.get("/api/voice/audio/..%2F.env").status_code == 404
    assert api.get("/api/voice/audio/" + "0" * 32 + ".wav").status_code == 404


def test_fixed_lines_are_complete_sentences_only():
    lines = fixed_lines(["hi-IN", "ta-IN"])
    texts = [t for t, _ in lines]
    assert phrases.say("not_heard", "hi-IN") in texts and phrases.say("calm", "ta-IN") in texts
    assert not any("{" in t for t in texts)
    assert phrases.PHRASES["hi-IN"]["sep"] not in texts and phrases.PHRASES["hi-IN"]["ground"] not in texts


def test_keyterms_are_english_spellings_only():
    terms = keyterms()
    assert "Velachery" in terms and "வேளச்சேரி" not in terms and len(terms) <= 200
    assert all(t.isascii() for t in terms)


def test_simulated_caller_line_uses_a_caller_voice(api, monkeypatch, tmp_path):
    caller = TimbreTTS(client=None, api_key="k", voices={"hi-IN": "Chitra"}, fallback_lang="hi-IN",
                       cache_dir=str(tmp_path / "cache"))
    said = []

    async def fake(text, lang):
        said.append((text, lang, caller.voice_for(lang)[1]))
        caller.cached_path(text, lang).write_bytes(WAV)
        return WAV
    monkeypatch.setattr(caller, "synthesize", fake)
    monkeypatch.setitem(main.voice, "caller_tts", caller)
    r = api.post("/api/voice/say", json={"text": "हम वेलाचेरी में हैं", "lang": "hi-IN"})
    assert r.status_code == 200
    assert said == [("हम वेलाचेरी में हैं", "hi-IN", "Chitra")]
    assert api.get(r.json()["audio"]).content == WAV
    assert api.post("/api/voice/say", json={"text": " ", "lang": "hi-IN"}).status_code == 400


def test_requests_to_prisma_dont_change_with_the_call_language(api):
    """Shaping the request by the call's language made one wrong guess stick (Hindi in Tamil letters)."""
    call = start(api)
    api.stt.queue += [("हमारे घर में पानी भर गया है, हम वेलाचेरी में हैं", "hi-IN"), ("चार लोग", "hi-IN")]
    api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"a")
    api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"b")
    assert main.sessions[call["call_id"]].ticket.language == "hi-IN"
    assert api.stt.hints == [{}, {}]       # no per-call hints or place names: Prisma's defaults every turn



def test_hindi_written_in_tamil_letters_is_answered_in_hindi_with_the_hindi_voice(api, monkeypatch):
    class HindiLLM:
        def extract(self, text, last_question, known):
            return Extraction(locality="Velachery", spoken_language="hi-IN", ack="ठीक है")
    monkeypatch.setattr(main, "llm", HindiLLM())
    call = start(api)
    api.spoken.clear()
    api.stt.queue.append(("பச்சாவோ பச்சாவோ முஜே பச்சாவோ ப்ளீஸ்", "ta-IN"))
    res = api.post(f"/api/voice/calls/{call['call_id']}/turn", content=b"a").json()
    assert res["reply_lang"] == "hi-IN" and res["lang_check"]["heard"] == "hi-IN"
    assert api.spoken and all(lang == "hi-IN" for _, lang in api.spoken)   # Yashvi, not the Tamil voice