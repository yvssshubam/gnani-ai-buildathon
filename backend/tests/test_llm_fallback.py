"""A second endpoint answers when the first can't (e.g. Evon on a notebook that stopped, Groq behind it),
and notes can run on their own endpoint. Fake HTTP servers, no API keys."""
import json

import httpx
import pytest

from app.config import settings
from app.llm import OpenAICompatLLM

SAVED = ("llm_api_key", "llm_model", "llm_reasoning_effort", "llm_extra_body", "llm_fallback_base_url",
         "llm_fallback_api_key", "llm_fallback_model", "llm_fallback_notes_model", "llm_fallback_cooldown",
         "notes_llm_base_url", "notes_llm_api_key", "notes_llm_extra_body", "notes_llm_model")


@pytest.fixture(autouse=True)
def restore_settings():
    before = {k: getattr(settings, k) for k in SAVED}
    yield
    for k, v in before.items():
        setattr(settings, k, v)


def reply(content: str):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def client(base: str, handler):
    return httpx.Client(base_url=base, transport=httpx.MockTransport(handler))


def make(primary, fallback=None, notes=None):
    """An LLM whose endpoints are fake servers. Each handler also records the bodies it was sent."""
    settings.llm_api_key = "k"
    settings.llm_model = "evon"
    settings.llm_reasoning_effort = ""
    if fallback:
        settings.llm_fallback_base_url = "https://fallback.local/v1"
        settings.llm_fallback_api_key = "k2"
        settings.llm_fallback_model = "openai/gpt-oss-20b"
        settings.llm_fallback_notes_model = "openai/gpt-oss-120b"
    if notes:
        settings.notes_llm_base_url = "https://notes.local/v1"
    llm = OpenAICompatLLM()
    llm.client = client("https://primary.local/v1", primary)
    if fallback:
        llm.fallback = client("https://fallback.local/v1", fallback)
    if notes:
        llm.notes_client = client("https://notes.local/v1", notes)
    return llm


def recorder(response):
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return response(request) if callable(response) else response
    handler.seen = seen
    return handler


EXTRACT = json.dumps({"people_count": 4})


def test_primary_answers_and_fallback_is_not_called():
    primary, fallback = recorder(reply(EXTRACT)), recorder(reply(EXTRACT))
    llm = make(primary, fallback)
    assert llm.extract("चार लोग हैं", None, "").people_count == 4
    assert len(primary.seen) == 1 and fallback.seen == []
    assert llm.calls == {"live": 1, "notes": 0, "fallback": 0}


def test_dead_primary_falls_back_within_the_same_turn():
    def dead(request):
        raise httpx.ConnectError("tunnel closed")
    fallback = recorder(reply(EXTRACT))
    llm = make(dead, fallback)
    e = llm.extract("चार लोग हैं", None, "")
    assert e.people_count == 4 and e.llm_failed is False     # the caller never notices
    assert fallback.seen[0]["model"] == "openai/gpt-oss-20b"
    assert fallback.seen[0]["reasoning_effort"] == "low"      # the gpt-oss rule still applies there
    assert llm.calls["fallback"] == 1


def test_unreachable_primary_is_skipped_for_the_cooldown():
    hits = []

    def dead(request):
        hits.append(1)
        return httpx.Response(530, text="tunnel error")
    llm = make(dead, recorder(reply(EXTRACT)))
    llm.extract("a", None, "")
    llm.extract("b", None, "")
    llm.extract("c", None, "")
    assert len(hits) == 1          # only the first turn paid for the dead endpoint
    llm.down_until["live"] = 0.0   # cooldown over: the primary is tried again
    llm.extract("d", None, "")
    assert len(hits) == 2


def test_empty_reply_falls_back_but_does_not_mark_the_primary_down():
    primary, fallback = recorder(reply("")), recorder(reply(EXTRACT))   # all tokens spent thinking
    llm = make(primary, fallback)
    assert llm.extract("a", None, "").people_count == 4
    assert llm.down_until.get("live", 0.0) == 0.0
    llm.extract("b", None, "")
    assert len(primary.seen) == 2  # still tried first on the next turn


def test_both_endpoints_down_is_still_a_safe_failed_extract():
    down = lambda request: httpx.Response(503, text="down")
    e = make(down, down).extract("a", None, "")
    assert e.unclear is True and e.llm_failed is True


def test_notes_job_uses_the_fallback_notes_model():
    def dead(request):
        raise httpx.ReadTimeout("slow")
    fallback = recorder(reply(json.dumps({"summary": "ok"})))
    llm = make(dead, fallback)
    out, _ = llm.chat_json("sys", "user", model="evon")
    assert out == {"summary": "ok"}
    assert fallback.seen[0]["model"] == "openai/gpt-oss-120b"


def test_extra_body_goes_to_the_primary_only():
    settings.llm_extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    primary, fallback = recorder(httpx.Response(500, text="x")), recorder(reply(EXTRACT))
    llm = make(primary, fallback)
    llm.extract("a", None, "")
    assert primary.seen[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in fallback.seen[0]


def test_notes_can_run_on_their_own_endpoint_while_the_live_call_stays_put():
    settings.notes_llm_model = "evon-notes"
    settings.notes_llm_extra_body = {"think": False}
    primary = recorder(reply(EXTRACT))
    notes = recorder(reply(json.dumps({"summary": "four people"})))
    llm = make(primary, notes=notes)
    llm.extract("a", None, "")
    out, _ = llm.chat_json("sys", "user", model=settings.notes_llm_model)
    assert out == {"summary": "four people"}
    assert len(primary.seen) == 1 and primary.seen[0]["model"] == "evon"
    assert notes.seen[0]["model"] == "evon-notes" and notes.seen[0]["think"] is False
    assert llm.calls == {"live": 1, "notes": 1, "fallback": 0}


def test_live_reasoning_effort_is_not_sent_to_the_fallback():
    settings_effort = "none"   # a value meant for the self-hosted model
    primary, fallback = recorder(httpx.Response(502, text="x")), recorder(reply(EXTRACT))
    llm = make(primary, fallback)
    settings.llm_reasoning_effort = settings_effort
    llm.extract("a", None, "")
    assert primary.seen[0]["reasoning_effort"] == "none"
    assert fallback.seen[0]["reasoning_effort"] == "low"
