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
import unicodedata
from typing import Optional, Protocol

import httpx

from . import prompts
from .config import settings
from .gazetteer import LOCALITIES, clean_pincode
from .language import LANG_NAMES, normalize_lang
from .models import NEED_TYPES, VULNERABLE_TYPES, WATER_LEVELS, Extraction

log = logging.getLogger("llm")


class LLM(Protocol):
    def extract(self, utterance: str, last_question: Optional[str], known_summary: str) -> Extraction: ...
    def phrase(self, instruction: str, lang: str, utterance: Optional[str], fallback_text: str) -> str: ...


# A street / building / landmark "name" made only of these is not a name ("our house",
# "మా ఇల్లుంది", "हमारा घर", "எங்க வீடு"). Matched as word beginnings, in English letters and
# in each script, because the LLM sometimes copies the words into the name field.
_GENERIC_STEMS = (
    # English
    "house", "home", "building", "flat", "apartment", "place", "area", "street", "road", "here", "there",
    # Hindi in English letters / Devanagari
    "ghar", "makaan", "makan", "yahan", "wahan", "घर", "मकान", "यहाँ", "यहां", "वहाँ", "बिल्डिंग",
    # Telugu in English letters / Telugu
    "illu", "illa", "intlo", "inti", "ikkada", "akkada", "ఇల్ల", "ఇంట", "ఇక్కడ", "అక్కడ", "బిల్డింగ్",
    # Tamil in English letters / Tamil
    "veedu", "veetu", "veettu", "inga", "anga", "வீட", "இங்க", "அங்க", "பில்டிங்",
)
_FILLER_WORDS = {
    "our", "my", "the", "a", "an", "this", "that", "it", "its", "it's", "is", "own", "same", "just", "only", "means",
    "mera", "meri", "mere", "hamara", "hamari", "hamare", "apna", "apni", "hai", "wala", "wali", "matlab",
    "मेरा", "मेरी", "मेरे", "हमारा", "हमारी", "हमारे", "अपना", "अपनी", "है", "वाला", "मतलब", "का", "की", "के",
    "maa", "naa", "mana", "manadi", "undi", "ante", "మా", "నా", "మన", "ఉంది", "అంటే",
    "enga", "en", "ennoda", "engaloda", "irukku", "ellam", "எங்க", "என்", "என்னோட", "இருக்கு", "அதான்",
}


def is_generic_place(value) -> bool:
    """True if a place name is only everyday words: "Maa Illundhi" (= "it's our house")."""
    if not isinstance(value, str):
        return False
    words = "".join(c.lower() if (c.isalnum() or unicodedata.category(c).startswith("M") or c == "'") else " "
                    for c in value).split()
    if not words:
        return True
    return all(w in _FILLER_WORDS or w.startswith(_GENERIC_STEMS) for w in words)


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
    if data.get("caller_question") not in ("when_help", "stay_or_move", "electricity", "animal", "rephrase",
                                           "go_ahead", "other"):
        data.pop("caller_question", None)
    if data.get("panic") not in ("low", "high"):
        data.pop("panic", None)
    data["spoken_language"] = normalize_lang(data.get("spoken_language"))
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
    data["pincode"] = clean_pincode(data.get("pincode"))
    if isinstance(data.get("reply"), str):
        data["reply"] = data["reply"].strip().strip('"').strip() or None
    else:
        data.pop("reply", None)
    for key in ("street", "building", "landmark"):
        # "building? it's our house" is not a building name: drop it, and its native copy
        if is_generic_place(data.get(key)) or (not data.get(key) and is_generic_place(data.get(f"{key}_native"))):
            data.pop(key, None)
            data.pop(f"{key}_native", None)
    for key in ("water_rising", "injured", "medical_emergency", "structure_unsafe", "trapped",
                "correction", "asks_for_human", "unclear", "dont_know"):
        if key in data and not isinstance(data[key], bool):
            data.pop(key)
    return Extraction(**data)


def _retry_after(r: httpx.Response, default: float) -> float:
    """Seconds Groq asks us to wait: the retry-after header, or "Please try again in 1.7475s" in the body."""
    try:
        if r.headers.get("retry-after"):
            return max(0.0, float(r.headers["retry-after"]))
    except ValueError:
        pass
    m = re.search(r"try again in ([\d.]+)(ms|s)", r.text or "")
    if m:
        value = float(m.group(1))
        return value / 1000 if m.group(2) == "ms" else value
    return default


def _json_from_text(text: str) -> dict:
    """The JSON object in a plain-text reply (used when JSON mode itself failed)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[start:end + 1])


def _json_mode_failed(err: Exception) -> bool:
    """Groq's 400 json_validate_failed: the model wrote no valid JSON (often nothing at all)."""
    return isinstance(err, httpx.HTTPStatusError) and err.response.status_code == 400 \
        and "json_validate_failed" in (err.response.text or "")


def _retry_wait(err: Exception) -> Optional[float]:
    """Seconds to wait before one retry of the live extract, or None if retrying won't help.
    A caller is waiting, so the wait is capped at 4 s, and a timeout (already 8 s) isn't retried."""
    if isinstance(err, httpx.HTTPStatusError):
        status = err.response.status_code
        if status == 429:
            return min(4.0, _retry_after(err.response, default=1.0) + 0.2)
        return 0.3 if status >= 500 or status == 400 else None   # 400: Groq's json_validate_failed
    if isinstance(err, ValueError):   # empty content, or JSON that didn't parse
        return 0.0
    return None


def _unreachable(err: Exception) -> bool:
    """The endpoint itself is down (no connection, a timeout, a dead tunnel), not just this request."""
    if isinstance(err, httpx.HTTPStatusError):
        return err.response.status_code >= 500
    return isinstance(err, httpx.TransportError)


class OpenAICompatLLM:
    """Up to three endpoints, all OpenAI-compatible:
      - live:     LLM_BASE_URL, for the caller's turn (extract, phrase)
      - notes:    NOTES_LLM_BASE_URL if set, for notes and the simulated caller; else the live one
      - fallback: LLM_FALLBACK_BASE_URL if set, tried when the endpoint a job belongs to fails
    With none of the optional ones set, this behaves exactly as a single endpoint."""

    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is empty. Set it in backend/.env or use LLM_PROVIDER=fake.")
        self.client = self._client(settings.llm_base_url, settings.llm_api_key)
        self.notes_client: Optional[httpx.Client] = None
        if settings.notes_llm_base_url:
            self.notes_client = self._client(settings.notes_llm_base_url,
                                             settings.notes_llm_api_key or settings.llm_api_key)
        self.fallback: Optional[httpx.Client] = None
        if settings.llm_fallback_base_url and settings.llm_fallback_api_key and settings.llm_fallback_model:
            self.fallback = self._client(settings.llm_fallback_base_url, settings.llm_fallback_api_key)
        # After a 429, background work (notes) waits until this time so the live call gets the quota.
        self.cooldown_until = 0.0
        # An endpoint that was unreachable is skipped until this time (per endpoint name).
        self.down_until: dict[str, float] = {}
        # How many answers came from where: shown at /api/health, so a demo can say which model spoke.
        self.calls: dict[str, int] = {"live": 0, "notes": 0, "fallback": 0}

    @staticmethod
    def _client(base_url: str, api_key: str) -> httpx.Client:
        return httpx.Client(base_url=base_url.rstrip("/"), headers={"Authorization": f"Bearer {api_key}"},
                            timeout=settings.llm_timeout)

    def _post(self, client: httpx.Client, where: str, model: str, messages: list[dict], json_mode: bool,
              max_tokens: Optional[int], timeout: Optional[float] = None) -> tuple[str, int]:
        """One request to one endpoint. Raises on an HTTP error or an empty reply."""
        body = {"model": model, "messages": messages, "temperature": 0.2,
                "max_tokens": max_tokens or settings.llm_max_tokens}
        # LLM_REASONING_EFFORT belongs to the live endpoint's model; elsewhere only the gpt-oss rule applies
        effort = (settings.llm_reasoning_effort if where == "live" else "") or ("low" if "gpt-oss" in model else "")
        if effort:
            # gpt-oss reasons before it answers; on "medium" it can spend the whole allowance
            # thinking and write nothing (Groq then fails JSON mode with an empty generation)
            body["reasoning_effort"] = effort
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if where == "live":
            body.update(settings.llm_extra_body)
        elif where == "notes":
            body.update(settings.notes_llm_extra_body)
        t0 = time.perf_counter()
        r = client.post("/chat/completions", json=body, **({"timeout": timeout} if timeout else {}))
        if r.status_code == 429:
            self.cooldown_until = time.time() + _retry_after(r, default=10.0)
        if r.status_code >= 400:
            log.warning("LLM HTTP %s (%s): %s", r.status_code, where, r.text[:300])
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"].get("content") or ""
        tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
        log.info("LLM %s call (%s, %s): %.0f ms, %s tokens", "extract" if json_mode else "phrase",
                 where, model, (time.perf_counter() - t0) * 1000, tokens)
        if not content.strip():
            raise ValueError("LLM returned empty content (token limit used up by reasoning?)")
        self.calls[where] = self.calls.get(where, 0) + 1
        return content, tokens

    def _chat(self, messages: list[dict], json_mode: bool, max_tokens: Optional[int] = None,
              model: Optional[str] = None) -> tuple[str, int]:
        # No model given = the caller's live turn. A model given = a background job (notes, the
        # simulated caller), which may have its own endpoint and can wait longer.
        live = model is None
        model = model or settings.llm_model
        if live or self.notes_client is None:
            where, client = "live", self.client
        else:
            where, client = "notes", self.notes_client
        timeout = None if live else settings.notes_llm_timeout
        fallback = self.fallback if self.fallback is not None and self.fallback.base_url != client.base_url else None
        if fallback is None:
            return self._post(client, where, model, messages, json_mode, max_tokens, timeout)

        if time.time() >= self.down_until.get(where, 0.0):
            try:
                return self._post(client, where, model, messages, json_mode, max_tokens, timeout)
            except (httpx.HTTPError, ValueError) as err:
                if _unreachable(err):
                    self.down_until[where] = time.time() + settings.llm_fallback_cooldown
                log.warning("LLM %s endpoint failed, using the fallback: %s", where, err)
        fb_model = settings.llm_fallback_model if live else (settings.llm_fallback_notes_model or settings.llm_fallback_model)
        return self._post(fallback, "fallback", fb_model, messages, json_mode, max_tokens, timeout)

    def extract(self, utterance, last_question, known_summary) -> Extraction:
        messages = [
            {"role": "system", "content": prompts.EXTRACT_SYSTEM},
            {"role": "user", "content": prompts.extract_user_prompt(utterance, last_question, known_summary)},
        ]
        json_mode = True
        for attempt in (1, 2):
            try:
                out, tokens = self._chat(messages, json_mode=json_mode, max_tokens=settings.llm_extract_max_tokens)
                e = clean_extraction(json.loads(out) if json_mode else _json_from_text(out))
                e.tokens_used = tokens
                return e
            except Exception as err:  # network error, bad JSON, rate limit...
                if _json_mode_failed(err):
                    json_mode = False      # retry as plain text and pull the JSON out of it
                wait = _retry_wait(err)
                if attempt == 1 and wait is not None:
                    log.warning("extract failed, retrying in %.1f s: %s", wait, err)
                    time.sleep(wait)
                    continue
                log.warning("extract failed: %s", err)
                return Extraction(unclear=True, llm_failed=True)
        return Extraction(unclear=True, llm_failed=True)

    def chat_json(self, system: str, user: str, model: Optional[str] = None,
                  max_tokens: Optional[int] = None) -> tuple[dict, int]:
        """Any small JSON job (call notes, the notes check). Raises on failure: callers fall back."""
        out, tokens = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                 json_mode=True, model=model, max_tokens=max_tokens)
        return json.loads(out), tokens

    def chat_text(self, system: str, user: str, model: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
        """Any small text job (the simulated caller). Raises on failure. `model` picks another model,
        which on Groq has its own rate limit (the stress test's caller uses that)."""
        out, _ = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                            json_mode=False, model=model, max_tokens=max_tokens)
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

    def chat_json(self, system: str, user: str, **kw) -> tuple[dict, int]:
        raise NotImplementedError("the offline fake LLM has no free-form jobs; callers use their rule-based fallback")

    def chat_text(self, system: str, user: str, **kw) -> str:
        raise NotImplementedError("the offline fake LLM has no free-form jobs; callers use their rule-based fallback")


def make_llm() -> LLM:
    if settings.llm_provider == "openai_compat":
        return OpenAICompatLLM()
    return FakeLLM()