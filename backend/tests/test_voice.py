"""Prisma/Timbre clients against a fake Gnani server (no network, no credits)."""
import asyncio
import json

import httpx
import pytest

from app.voice import gnani_http
from app.voice.gnani_http import GnaniError
from app.voice.stt import PrismaSTT
from app.voice.tts import TimbreTTS

WAV = b"RIFF" + b"\0" * 60  # big enough to pass the "is audio" check


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(gnani_http, "BACKOFF_SECONDS", (0, 0, 0))


def run(coro):
    return asyncio.run(coro)


def fake_gnani(handler):
    """AsyncClient whose requests go to handler(request) -> httpx.Response. Records requests."""
    seen = []

    def wrapped(request):
        request.read()
        seen.append(request)
        return handler(request, len(seen))
    return httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), seen


def stt_ok(request, n):
    return httpx.Response(200, json={"success": True, "transcript": " हम वेलाचेरी में हैं ",
                                     "detected_language_code": "hi-IN", "end_to_end_latency": 0.7,
                                     "request_id": "r1"})


# ---------- STT ----------

def test_stt_sends_the_call_settings_and_parses_language():
    client, seen = fake_gnani(stt_ok)
    stt = PrismaSTT(client, "k1", base_url="https://g.test", model="prisma-v3.0",
                    languages="ta-IN,hi-IN,en-IN,te-IN", fmt="codemix",
                    keyterms=["Velachery", "வேளச்சேரி", "Velachery"])
    t = run(stt.transcribe(b"audio", previous_text="आप कहाँ हैं?"))

    assert (t.text, t.language, t.server_seconds) == ("हम वेलाचेरी में हैं", "hi-IN", 0.7)
    req = seen[0]
    assert str(req.url) == "https://g.test/stt/v3"
    assert req.headers["X-API-Key-ID"] == "k1"
    body = req.content.decode("utf-8")
    for expected in ['name="model"', "prisma-v3.0", 'name="language_code"', "ta-IN,hi-IN,en-IN,te-IN",
                     'name="format"', "codemix", 'name="previous_text"', "आप कहाँ हैं?",
                     'name="audio_file"']:
        assert expected in body
    assert json.dumps(["Velachery", "வேளச்சேரி"], ensure_ascii=False) in body  # deduplicated


def test_stt_empty_clip_gives_empty_text_and_no_language():
    client, _ = fake_gnani(lambda r, n: httpx.Response(200, json={"success": True, "transcript": ""}))
    t = run(PrismaSTT(client, "k").transcribe(b"silence"))
    assert t.text == "" and t.language is None


def test_stt_context_is_cut_to_last_600_chars():
    client, seen = fake_gnani(stt_ok)
    run(PrismaSTT(client, "k").transcribe(b"a", previous_text="x" * 700 + "END"))
    assert ("x" * 597 + "END") in seen[0].content.decode() and "x" * 598 + "END" not in seen[0].content.decode()


def test_stt_retries_429_then_succeeds():
    def handler(r, n):
        if n == 1:
            return httpx.Response(429, json={"detail": {"error_code": "RATE_LIMITED", "message": "busy"}})
        return stt_ok(r, n)
    client, seen = fake_gnani(handler)
    assert run(PrismaSTT(client, "k").transcribe(b"a")).text
    assert len(seen) == 2


def test_stt_gives_up_after_repeated_504():
    client, seen = fake_gnani(lambda r, n: httpx.Response(504, json={"code": "UPSTREAM_TIMEOUT"}))
    with pytest.raises(GnaniError) as e:
        run(PrismaSTT(client, "k").transcribe(b"a"))
    assert e.value.status == 504 and e.value.code == "UPSTREAM_TIMEOUT"
    assert len(seen) == 4  # first try + 3 retries


def test_stt_bad_key_fails_fast_with_a_hint():
    client, seen = fake_gnani(lambda r, n: httpx.Response(
        401, json={"detail": {"error_code": "INVALID_API_KEY", "message": "bad key", "status_code": 401}}))
    with pytest.raises(GnaniError) as e:
        run(PrismaSTT(client, "k").transcribe(b"a"))
    assert e.value.code == "INVALID_API_KEY" and not e.value.retryable
    assert "X-API-Key-ID" in str(e.value)
    assert len(seen) == 1


def test_stt_400_error_envelope_is_parsed():
    client, _ = fake_gnani(lambda r, n: httpx.Response(
        400, json={"success": False, "error": {"type": "INVALID_LANGUAGE_CODE", "message": "hi-in"}}))
    with pytest.raises(GnaniError) as e:
        run(PrismaSTT(client, "k").transcribe(b"a"))
    assert e.value.code == "INVALID_LANGUAGE_CODE"


# ---------- TTS ----------

def tts_ok(request, n):
    return httpx.Response(200, content=WAV, headers={"content-type": "audio/wav"})


def make_tts(tmp_path, client):
    return TimbreTTS(client, "k", base_url="https://g.test", model="timbre-v2.5",
                     voices={"hi-IN": "Yashvi", "ta-IN": "Noopur"}, fallback_lang="hi-IN",
                     sample_rate=16000, speed=1.0, cache_dir=str(tmp_path / "cache"))


def test_tts_request_body(tmp_path):
    client, seen = fake_gnani(tts_ok)
    audio = run(make_tts(tmp_path, client).synthesize("नमस्ते", "ta-IN"))
    assert audio == WAV
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://g.test/api/v1/tts/inference"
    assert body["voice"] == "Noopur" and body["language"] == "ta-IN" and body["model"] == "timbre-v2.5"
    assert body["audio_config"] == {"sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                                    "encoding": "linear_pcm", "container": "wav"}


def test_tts_same_line_is_paid_for_once(tmp_path):
    client, seen = fake_gnani(tts_ok)
    tts = make_tts(tmp_path, client)
    run(tts.synthesize("ठीक है", "hi-IN"))
    run(tts.synthesize(" ठीक है ", "hi-IN"))  # same line, extra spaces
    assert len(seen) == 1 and (tts.api_calls, tts.cache_hits) == (1, 1)
    # a new TimbreTTS (server restart) still finds it on disk
    assert run(make_tts(tmp_path, client).synthesize("ठीक है", "hi-IN")) == WAV
    assert len(seen) == 1


def test_tts_parallel_calls_for_one_new_line_make_one_request(tmp_path):
    client, seen = fake_gnani(tts_ok)
    tts = make_tts(tmp_path, client)

    async def both():
        return await asyncio.gather(tts.synthesize("नया", "hi-IN"), tts.synthesize("नया", "hi-IN"))
    assert run(both()) == [WAV, WAV]
    assert len(seen) == 1


def test_tts_language_without_voice_uses_fallback(tmp_path):
    client, seen = fake_gnani(tts_ok)
    run(make_tts(tmp_path, client).synthesize("hello", "kn-IN"))
    body = json.loads(seen[0].content)
    assert (body["language"], body["voice"]) == ("hi-IN", "Yashvi")


def test_tts_non_audio_200_is_an_error_and_not_cached(tmp_path):
    client, _ = fake_gnani(lambda r, n: httpx.Response(200, json={"oops": True}))
    tts = make_tts(tmp_path, client)
    with pytest.raises(GnaniError):
        run(tts.synthesize("नमस्ते", "hi-IN"))
    assert not tts.cached_path("नमस्ते", "hi-IN").exists()


def test_tts_prewarm_skips_cached_lines(tmp_path):
    client, seen = fake_gnani(tts_ok)
    tts = make_tts(tmp_path, client)
    lines = [("एक", "hi-IN"), ("दो", "hi-IN"), ("एक", "hi-IN"), ("", "hi-IN")]
    assert run(tts.prewarm(lines)) == 2
    assert run(tts.prewarm(lines)) == 0
    assert len(seen) == 2
