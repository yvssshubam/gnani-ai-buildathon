"""The real LLM adapter, tested against a fake HTTP server (no API key needed)."""
import json

import httpx

from app.config import settings
from app.llm import OpenAICompatLLM


def make_llm(handler):
    settings.llm_api_key = "test-key"
    llm = OpenAICompatLLM()
    llm.client = httpx.Client(base_url="https://fake.local/v1", transport=httpx.MockTransport(handler))
    return llm


def reply(content: str):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_extract_parses_and_cleans_json():
    def handler(request):
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        return reply(json.dumps({
            "locality": "Velachery", "people_count": "4", "vulnerable": ["elderly", "alien"],
            "water_level": "knee", "needs": ["rescue", "pizza"], "injured": False,
        }))

    e = make_llm(handler).extract("வேளச்சேரியில் நாலு பேர் இருக்கோம்", None, "")
    assert e.locality == "Velachery"
    assert e.people_count == 4
    assert e.vulnerable == ["elderly"]  # unknown values dropped
    assert e.needs == ["rescue"]
    assert e.water_level == "knee"
    assert e.injured is False


def test_extract_bad_json_is_marked_unclear():
    e = make_llm(lambda r: reply("not json at all")).extract("...", None, "")
    assert e.unclear is True


def test_phrase_falls_back_to_english_on_error():
    llm = make_llm(lambda r: httpx.Response(500, json={"error": "down"}))
    assert llm.phrase("Ask how many people", "ta-IN", "hi", "How many people?") == "How many people?"


def test_reasoning_effort_sent_only_when_set():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return reply("ok")

    settings.llm_reasoning_effort = "low"
    make_llm(handler).phrase("x", "en-IN", "hi", "fallback")
    assert seen["reasoning_effort"] == "low" and seen["max_tokens"] >= 512
    seen.clear()
    settings.llm_reasoning_effort = ""
    make_llm(handler).phrase("x", "en-IN", "hi", "fallback")
    assert "reasoning_effort" not in seen


def test_empty_reply_uses_fallback():
    llm = make_llm(lambda r: httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}))
    assert llm.phrase("x", "ta-IN", "hi", "How many people?") == "How many people?"
    assert llm.extract("...", None, "").unclear is True


def test_phrase_asks_for_target_language():
    def handler(request):
        system = json.loads(request.content)["messages"][0]["content"]
        assert "Tamil" in system
        return reply("எத்தனை பேர் இருக்கீங்க?")

    assert make_llm(handler).phrase("Ask how many people", "ta-IN", "hi", "x") == "எத்தனை பேர் இருக்கீங்க?"

def test_extract_retries_once_after_a_rate_limit(monkeypatch):
    import app.llm as llm_mod
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "rate limit"}})
        return reply(json.dumps({"injured": False, "spoken_language": "hi"}))

    llm = make_llm(handler)
    e = llm.extract("किसी को भी चोट नहीं लगी है", "Is anyone hurt?", "")
    assert len(calls) == 2 and e.injured is False and e.spoken_language == "hi-IN" and not e.llm_failed
    assert llm.cooldown_until > 0            # notes wait for the quota to come back


def test_extract_gives_up_after_two_failures_and_says_so(monkeypatch):
    import app.llm as llm_mod
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    e = make_llm(handler).extract("...", None, "")
    assert len(calls) == 2 and e.unclear and e.llm_failed


def test_a_wrong_key_is_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    e = make_llm(handler).extract("...", None, "")
    assert len(calls) == 1 and e.llm_failed