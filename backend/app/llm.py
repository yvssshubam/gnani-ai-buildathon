"""The LLM does two small jobs only:
  1. extract(): pull facts out of one caller utterance (JSON)
  2. phrase():  say a decided action kindly, in the caller's language

It never decides what to ask, the priority, or when to end the call. Code does.

Two implementations:
  - OpenAICompatLLM: any OpenAI-compatible chat API
  - FakeLLM: offline, English-only regex rules, for tests and quick checks
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional, Protocol

import httpx

from . import prompts
from .config import settings
from .gazetteer import LOCALITIES
from .language import LANG_NAMES
from .models import NEED_TYPES, VULNERABLE_TYPES, WATER_LEVELS, Extraction

log = logging.getLogger("llm")


class LLM(Protocol):
    def extract(self, utterance: str, last_question: Optional[str], known_summary: str) -> Extraction: ...
    def phrase(self, instruction: str, lang: str, utterance: Optional[str], fallback_text: str) -> str: ...


def clean_extraction(raw: dict) -> Extraction:
    """Validate LLM output: drop unknown values instead of trusting them."""
    data = {k: v for k, v in raw.items()
            if k in Extraction.model_fields and k != "tokens_used" and v not in ("", "null", None)}
    if data.get("water_level") not in WATER_LEVELS:
        data.pop("water_level", None)
    data["vulnerable"] = [v for v in data.get("vulnerable") or [] if v in VULNERABLE_TYPES]
    data["needs"] = [n for n in data.get("needs") or [] if n in NEED_TYPES]
    if data.get("confirmation") not in ("yes", "no"):
        data.pop("confirmation", None)
    if data.get("caller_question") not in ("when_help", "stay_or_move", "electricity", "animal", "other"):
        data.pop("caller_question", None)
    if data.get("panic") not in ("low", "high"):
        data.pop("panic", None)
    if isinstance(data.get("ack"), str):
        data["ack"] = data["ack"].strip().strip('"').strip() or None
    else:
        data.pop("ack", None)
    pc = data.get("people_count")
    try:
        data["people_count"] = int(pc) if pc is not None else None
        if data["people_count"] is not None and not (0 < data["people_count"] < 500):
            data["people_count"] = None
    except (TypeError, ValueError):
        data["people_count"] = None
    for key in ("locality", "street", "door_no", "building", "floor", "landmark", "medical_need",
                "street_native", "building_native", "landmark_native"):
        if key in data and data[key] is not None:
            data[key] = str(data[key]).strip() or None
    for key in ("water_rising", "injured", "medical_emergency", "structure_unsafe", "trapped",
                "correction", "asks_for_human", "unclear", "dont_know"):
        if key in data and not isinstance(data[key], bool):
            data.pop(key)
    return Extraction(**data)


class OpenAICompatLLM:
    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is empty. Set it in backend/.env or use LLM_PROVIDER=fake.")
        self.client = httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout,
        )

    def _chat(self, messages: list[dict], json_mode: bool) -> tuple[str, int]:
        body = {"model": settings.llm_model, "messages": messages, "temperature": 0.2,
                "max_tokens": settings.llm_max_tokens}
        if settings.llm_reasoning_effort:
            body["reasoning_effort"] = settings.llm_reasoning_effort
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        r = self.client.post("/chat/completions", json=body)
        if r.status_code >= 400:
            log.warning("LLM HTTP %s: %s", r.status_code, r.text[:300])
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"].get("content") or ""
        tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
        log.info("LLM %s call: %.0f ms, %s tokens", "extract" if json_mode else "phrase",
                 (time.perf_counter() - t0) * 1000, tokens)
        if not content.strip():
            raise ValueError("LLM returned empty content (token limit used up by reasoning?)")
        return content, tokens

    def extract(self, utterance, last_question, known_summary) -> Extraction:
        try:
            out, tokens = self._chat(
                [
                    {"role": "system", "content": prompts.EXTRACT_SYSTEM},
                    {"role": "user", "content": prompts.extract_user_prompt(utterance, last_question, known_summary)},
                ],
                json_mode=True,
            )
            e = clean_extraction(json.loads(out))
            e.tokens_used = tokens
            return e
        except Exception as e:  # network error, bad JSON, rate limit...
            log.warning("extract failed: %s", e)
            return Extraction(unclear=True)

    def chat_json(self, system: str, user: str) -> tuple[dict, int]:
        """Any small JSON job (call notes, the notes check). Raises on failure: callers fall back."""
        out, tokens = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}], json_mode=True)
        return json.loads(out), tokens

    def chat_text(self, system: str, user: str) -> str:
        """Any small text job (the simulated caller). Raises on failure."""
        out, _ = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}], json_mode=False)
        return out.strip().strip('"')

    def phrase(self, instruction, lang, utterance, fallback_text) -> str:
        lang_name = LANG_NAMES.get(lang, "English")
        script_note = "" if lang == "en-IN" else f", written in {lang_name} script (English words like 'floor' may stay in English)"
        try:
            out, _ = self._chat(
                [
                    {"role": "system", "content": prompts.PHRASE_SYSTEM.format(
                        lang_name=lang_name, script_note=script_note, instruction=instruction)},
                    {"role": "user", "content": f"Caller just said: {utterance or '(nothing yet)'}"},
                ],
                json_mode=False,
            )
            return out.strip().strip('"') or fallback_text
        except Exception as e:
            log.warning("phrase failed, using English fallback: %s", e)
            return fallback_text


# ----------------------------------------------------------------------------
# Offline fake: simple English rules. Good enough to test the call flow.
# ----------------------------------------------------------------------------
_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "alone": 1, "just me": 1, "only me": 1}


class FakeLLM:
    def extract(self, utterance, last_question, known_summary) -> Extraction:
        t = utterance.lower()
        e: dict = {"vulnerable": [], "needs": []}

        for loc in LOCALITIES:
            if any(a in t for a in loc["aliases"]):
                e["locality"] = loc["name"]
                break
        if m := re.search(r"([a-z0-9]+(?: [a-z0-9]+)? (?:street|road|nagar main road|cross street))", t):
            e["street"] = m.group(1).title()
        if m := re.search(r"door (?:no\.?|number)? ?(\d+[a-z]?)", t):
            e["door_no"] = m.group(1)
        if m := re.search(r"(\w+) (?:apartments?|flats?|towers?)", t):
            e["building"] = m.group(0).title()
        if m := re.search(r"(ground|first|second|third|fourth|\d+(?:st|nd|rd|th)?) floor", t):
            e["floor"] = m.group(1)
        elif "terrace" in t or "roof" in t:
            e["floor"] = "terrace"
        if m := re.search(r"near (?:the |a )?([a-z ]*?(?:temple|church|mosque|school|bus stop|hospital))", t):
            e["landmark"] = m.group(1).strip().title()

        if m := re.search(r"(\d+) (?:people|persons|of us|members)", t) or re.search(r"we are (\d+)", t):
            e["people_count"] = int(m.group(1))
        else:
            for w, n in _NUM_WORDS.items():
                if re.search(rf"\b{w}\b (?:people|persons|of us|members)", t) or re.search(rf"we are {w}\b", t):
                    e["people_count"] = n
            if last_question and "people" in last_question.lower():
                if m := re.fullmatch(r"\s*(\d+)\s*\.?\s*", t):
                    e["people_count"] = int(m.group(1))
                elif t.strip(" .") in _NUM_WORDS:
                    e["people_count"] = _NUM_WORDS[t.strip(" .")]

        if re.search(r"grand(mother|father|ma|pa)|old (man|woman|lady|people)|elderly|paati|thatha", t):
            e["vulnerable"].append("elderly")
        if re.search(r"\bbaby\b|infant|newborn", t):
            e["vulnerable"].append("infant")
        if re.search(r"\bkids?\b|child|children", t):
            e["vulnerable"].append("child")
        if "pregnant" in t:
            e["vulnerable"].append("pregnant")
        if re.search(r"wheelchair|disabled|bedridden", t):
            e["vulnerable"].append("disabled")
        if m := re.search(r"(insulin|oxygen|dialysis|medicine|tablets)", t):
            e["medical_need"] = m.group(1)

        for level in ["roof", "neck", "chest", "waist", "knee", "ankle"]:
            if level in t and ("water" in t or (last_question and "water" in last_question.lower())):
                e["water_level"] = level
                break
        if "rising" in t or "increasing" in t or "coming up" in t:
            e["water_rising"] = True
        if re.search(r"injur|hurt|bleeding|broken", t):
            e["injured"] = not re.search(r"\bno(body|one)? (is )?(hurt|injured)|not (hurt|injured)", t)
        if re.search(r"unconscious|not breathing|chest pain|labou?r pain", t):
            e["medical_emergency"] = True
        if re.search(r"wall (is )?crack|collaps", t):
            e["structure_unsafe"] = True
        if re.search(r"stuck|trapped|stranded|can't (get|go) out|cannot (get|go) out", t):
            e["trapped"] = True
            e["needs"].append("rescue")
        if re.search(r"rescue|save us|help us|boat", t) and "rescue" not in e["needs"]:
            e["needs"].append("rescue")
        for need in ("food", "water", "medicine"):
            if re.search(rf"need {need}|no {need}|{need} needed", t):
                e["needs"].append(need)

        if last_question and last_question.startswith("readback"):
            if re.match(r"\s*(yes|yeah|correct|right|ok|okay|ama|aamaa|haan)\b", t):
                e["confirmation"] = "yes"
            elif re.match(r"\s*(no|wrong|not)\b", t):
                e["confirmation"] = "no"
                e["correction"] = any(k in e for k in ("locality", "street", "door_no", "building", "floor", "people_count"))
        if last_question and last_question.startswith("ask:danger") and re.match(r"\s*no\b", t):
            e.setdefault("injured", False)
        if last_question and last_question.startswith("ask:vulnerable") and re.match(r"\s*no\b", t):
            pass  # "no" = nobody vulnerable; the slot counts as answered once asked
        if re.search(r"real person|human|officer|talk to someone", t):
            e["asks_for_human"] = True
        if re.search(r"don'?t know|not sure|no idea", t):
            e["dont_know"] = True
        if re.search(r"when will|how long|how much time", t):
            e["caller_question"] = "when_help"
        elif re.search(r"should (we|i) (go|stay|leave|move)|go to the terrace", t):
            e["caller_question"] = "stay_or_move"
        elif re.search(r"snake|scorpion|dog", t):
            e["caller_question"] = "animal"
        elif re.search(r"current|electric|wire|shock", t):
            e["caller_question"] = "electricity"
        if re.search(r"please please|help help|!!!|crying|scared", t):
            e["panic"] = "high"

        found = {k: v for k, v in e.items()
                 if v not in (None, []) and not (v is False and k in ("correction", "asks_for_human", "dont_know"))}
        if not found:
            e["unclear"] = True
        return clean_extraction(e)

    def phrase(self, instruction, lang, utterance, fallback_text) -> str:
        return fallback_text

    def chat_json(self, system: str, user: str) -> tuple[dict, int]:
        raise NotImplementedError("the offline fake LLM has no free-form jobs; callers use their rule-based fallback")

    def chat_text(self, system: str, user: str) -> str:
        raise NotImplementedError("the offline fake LLM has no free-form jobs; callers use their rule-based fallback")


def make_llm() -> LLM:
    if settings.llm_provider == "openai_compat":
        return OpenAICompatLLM()
    return FakeLLM()