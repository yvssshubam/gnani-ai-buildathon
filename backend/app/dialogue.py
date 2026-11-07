"""The call engine: one CallSession per call.

Each caller turn:
  1. track language                 (sticky, see language.py)
  2. understand the reply:
       short answer ("4", "ஆமா", "முட்டி")  -> quick_parse, NO LLM call
       anything else                        -> llm.extract (1 LLM call)
  3. merge into ticket, resolve location, set priority with fixed rules
  4. CODE decides the next action (ask a slot / read back / close)
  5. say it with a FIXED, reviewed line in the caller's language (phrases.py)

So the LLM is used at most once per turn, and often not at all.

Ask order: immediate danger -> area -> street/house -> floor -> people -> vulnerable -> water level.
A caller can answer in any order; anything they already said is never asked again.
Each slot gets at most 2 attempts (the 2nd is simpler), then we move on.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from . import phrases, prompts
from .config import settings
from .gazetteer import resolve
from .language import LanguageTracker, detect_script_language, reply_language
from .llm import LLM
from .models import CallState, Extraction, LocConfidence, Status, Ticket, Turn
from .priority import assess
from .quick_parse import quick_parse
from .store import TicketStore

log = logging.getLogger("dialogue")

# Location is split so we only ever ask for the part that is still missing:
#   area (locality) -> street (street / house no / building, + floor) -> floor (if still missing)
SLOT_ORDER = ["danger", "area", "street", "floor", "people", "vulnerable", "vulnerable_who", "water"]
MAX_ATTEMPTS_BY_SLOT = {"floor": 1, "vulnerable_who": 1}
MAX_ATTEMPTS = 2
MAX_READBACKS = 3
# Hand over to a human after this many turns in a row with no new information.
STUCK_LIMIT = 3
STUCK_LIMIT_PANIC = 2
# When the caller is panicking, these slots switch straight to their simple yes/no version.
SIMPLE_WHEN_PANIC = {"danger", "area", "people", "vulnerable", "water"}
ANSWERABLE = {"when_help", "stay_or_move", "electricity", "animal"}
RECHECK_AFTER_MIN = 30
RECHECK_REASON = f"re-check water level in {RECHECK_AFTER_MIN} min (P2, water present)"

# An LLM acknowledgement is thrown away if it sounds like a promise or a time.
PROMISE_WORDS = ["minute", "hour", "soon", "on the way", "will come", "will reach", "coming",
                 "நிமிஷ", "நிமிட", "மணி நேர", "சீக்கிரம்", "வந்துடுவாங்க", "வருவாங்க", "வந்துட்டே",
                 "मिनट", "घंटे", "जल्द", "आ जाएग", "आएंगे", "आएगी", "पहुँच",
                 "నిమిష", "గంట", "త్వరలో", "వస్తారు", "వచ్చేస్తారు",
                 # clock times ("by 5 o'clock") - numbers alone are fine ("door number 5")
                 "o'clock", " am", " pm", "बजे", "மணிக்கு", "மணிக்குள்", "గంటలకు", "గంటల్లో"]


def check_ack(ack: Optional[str], lang: str) -> tuple[Optional[str], str]:
    """Accept the LLM's short acknowledgement only if it is short, in the right language and promises nothing
    (no times). Echoing a house number is fine.
    Returns (ack or None, reason)."""
    if not ack:
        return None, "missing"
    a = ack.strip()
    if len(a.split()) > 8 or len(a) > 80:
        return None, "too long"
    if "?" in a:
        return None, "question"
    if detect_script_language(a) != lang:
        return None, f"wrong language ({detect_script_language(a)})"
    low = a.lower()
    if any(w in low for w in PROMISE_WORDS):
        return None, "sounds like a promise"
    return (a if a[-1] in ".!।" else a + ("।" if lang == "hi-IN" else ".")), "ok"


def safe_ack(ack: Optional[str], lang: str) -> Optional[str]:
    return check_ack(ack, lang)[0]


@dataclass
class Action:
    kind: str                 # ask | readback | ask_correction | close | handoff
    slot: Optional[str] = None
    attempt: int = 1
    urgent_preface: bool = False

    @property
    def key(self) -> str:
        return f"ask:{self.slot}" if self.kind == "ask" else self.kind


def spoken_digits(ticket_id: str) -> str:
    return " ".join(ticket_id)


ACK_LANGUAGE = {
    "hi-IN": "Hindi, Devanagari script",
    "ta-IN": "Tamil, Tamil script",
    "te-IN": "Telugu, Telugu script",
    "en-IN": "English",
}


def known_summary(t: Ticket, reply_lang: Optional[str] = None) -> str:
    """Short English context for the extractor.
    Includes the call's language: one English sentence ("Church Road, first floor") in a Hindi
    call must still get a Hindi ack, and the extractor only sees this one sentence."""
    loc = t.location
    parts = []
    if reply_lang in ACK_LANGUAGE:
        parts.append(f"call language: {ACK_LANGUAGE[reply_lang]}")
    where = ", ".join(p for p in (loc.door_no, loc.building, loc.street, loc.locality, loc.floor, loc.landmark) if p)
    if where:
        parts.append(f"location: {where}")
    if t.people_count:
        parts.append(f"people: {t.people_count}")
    if t.vulnerable:
        parts.append(f"vulnerable: {', '.join(t.vulnerable)}")
    if t.danger.water_level:
        parts.append(f"water: {t.danger.water_level}")
    return "; ".join(parts)


def facts_snapshot(t: Ticket) -> str:
    """Everything we know that matters for rescue; used to detect 'no progress' turns."""
    loc = t.location
    return repr((loc.locality, loc.street, loc.door_no, loc.building, loc.floor, loc.landmark,
                 t.people_count, sorted(t.vulnerable), t.medical_need, sorted(t.needs),
                 t.danger.model_dump()))


def apply_extraction(t: Ticket, e: Extraction) -> None:
    loc = t.location
    location_changed = False
    for field in ("locality", "street", "door_no", "building", "floor", "landmark"):
        value = getattr(e, field)
        if value:
            if getattr(loc, field) != value:
                location_changed = True
            setattr(loc, field, value)
    for field in ("street_native", "building_native", "landmark_native"):
        value = getattr(e, field)
        if value and getattr(loc, field) != value:
            # A native-only answer ("नेहरू स्ट्रीट") is still new location info: resolve() turns it
            # into English letters. Clear the old English name so a corrected street replaces it.
            english = field.removesuffix("_native")
            if not getattr(e, english):
                setattr(loc, english, None)
            setattr(loc, field, value)
            location_changed = True
    if location_changed:
        loc.confirmed = False
        resolve(loc)

    if e.people_count is not None:
        t.people_count = e.people_count
    for v in e.vulnerable:
        if v not in t.vulnerable:
            t.vulnerable.append(v)
    if len(t.vulnerable) > 1 and "unspecified" in t.vulnerable:
        t.vulnerable.remove("unspecified")
    if e.medical_need:
        t.medical_need = e.medical_need
    for n in e.needs:
        if n not in t.needs:
            t.needs.append(n)

    d = t.danger
    if e.water_level:
        d.water_level = e.water_level
    for field in ("water_rising", "injured", "medical_emergency", "structure_unsafe", "trapped"):
        value = getattr(e, field)
        if value is not None:
            setattr(d, field, value)


class CallSession:
    def __init__(self, ticket: Ticket, llm: LLM, store: TicketStore):
        self.ticket = ticket
        self.llm = llm
        self.store = store
        self.lang = LanguageTracker()
        self.attempts: dict[str, int] = {s: 0 for s in SLOT_ORDER}
        self.last_action: Optional[Action] = None
        self.readbacks = 0
        self.turns = 0
        self.done = False
        self.llm_calls = 0
        self.tokens = 0
        self.panic = False      # becomes True once the caller sounds panicked, stays True
        self.calmed = False     # calming line said once per call
        self.ack_status = "-"
        self.stuck_turns = 0    # consecutive turns where we learned nothing new
        self.facts_changed = False  # did the last caller turn change any fact on the ticket
        self.questions_seen: set[str] = set()  # caller questions already answered this call
        self.last_dont_know = False            # was the previous caller turn "I don't know"

    # ------------------------------------------------------------------ public
    def greeting(self) -> str:
        text = prompts.GREETING["text"]
        self._log("agent", text, prompts.GREETING["lang"])
        self.store.save(self.ticket)
        return text

    def handle(self, text: str, detected_lang: Optional[str] = None) -> dict:
        if self.done:
            return self._result("", None)
        started = time.perf_counter()
        t = self.ticket
        self.turns += 1

        detected = detected_lang or detect_script_language(text)
        call_lang = self.lang.update(detected, text)
        reply_lang, needs_interpreter = reply_language(call_lang)
        t.language = call_lang
        t.needs_interpreter = t.needs_interpreter or needs_interpreter
        self._log("caller", text, detected)

        # Understand the reply: quick parse first, LLM only if needed
        last_key = self.last_action.key if self.last_action else None
        extraction = quick_parse(text, last_key)
        used_llm = extraction is None
        if used_llm:
            extraction = self.llm.extract(text, self._last_question(), known_summary(t, reply_lang))
            self.llm_calls += 1
            self.tokens += extraction.tokens_used
        before = facts_snapshot(t)
        apply_extraction(t, extraction)
        if "rescue" not in t.needs and (t.danger.trapped or t.danger.water_level in
                                        ("knee", "waist", "chest", "neck", "roof")):
            t.needs.append("rescue")

        was_escalated = t.escalate_to_human
        t.priority, t.priority_reasons, alert = assess(t)
        if extraction.asks_for_human:
            alert = True
            t.priority_reasons.append("caller asked for a person")
        t.escalate_to_human = was_escalated or alert

        new_panic = extraction.panic == "high" and not self.panic
        self.panic = self.panic or extraction.panic == "high"

        # Did this turn actually change a fact? (The LLM's `correction` flag alone isn't enough:
        # "nahi galat he" says something is wrong but gives no new details.)
        self.facts_changed = facts_snapshot(t) != before

        # Asking us something shows the caller is engaged, but only the FIRST time:
        # "boat kab aayegi?" asked again and again is a caller who is stuck.
        new_question = (extraction.caller_question in ANSWERABLE
                        and extraction.caller_question not in self.questions_seen)
        if extraction.caller_question:
            self.questions_seen.add(extraction.caller_question)

        # "I don't know" is a real answer once (many people don't know their street), but
        # "pata nahi" to question after question means a human should take over.
        new_dont_know = extraction.dont_know and not self.last_dont_know
        self.last_dont_know = bool(extraction.dont_know)

        progressed = (self.facts_changed or extraction.confirmation is not None
                      or extraction.correction or new_dont_know
                      or new_question
                      # a quick-parsed answer ("nahi", "4") counts; "don't know" is handled above
                      or (not used_llm and not extraction.dont_know))
        # Only count it as "stuck" if we asked something and got nothing new back.
        if progressed:
            self.stuck_turns = 0
        elif self.last_action is not None:
            self.stuck_turns += 1

        action = self._next_action(extraction)
        action.urgent_preface = t.escalate_to_human and not was_escalated

        reply = self._say(action, reply_lang, extraction, used_llm, new_panic)
        if action.kind == "close":
            self._finish()
        elif action.kind == "handoff":
            self._hand_off()
        self.last_action = action
        self._log("agent", reply, reply_lang)
        self.store.save(t)

        result = self._result(reply, action)
        result["turn_ms"] = round((time.perf_counter() - started) * 1000)
        result["used_llm"] = used_llm
        result["ack_status"] = self.ack_status
        result["llm_calls_total"] = self.llm_calls
        result["tokens_total"] = self.tokens
        return result

    def drop(self) -> Ticket:
        """Network cut mid-call: keep everything we have, flag for callback."""
        t = self.ticket
        if not self.done:
            t.call_state = CallState.DROPPED
            t.status = Status.NEEDS_CALLBACK
            t.followup_reasons.append("call dropped mid-conversation")
            self.done = True
            self.store.save(t)
        return t

    # ----------------------------------------------------------------- private
    def _slot_filled(self, slot: str) -> bool:
        t = self.ticket
        d = t.danger
        loc = t.location
        if slot == "danger":
            return any(v is not None for v in (d.injured, d.medical_emergency, d.water_rising,
                                                d.structure_unsafe, d.trapped)) or d.water_level is not None
        if slot == "area":
            return loc.locality is not None and loc.lat is not None
        if slot == "street":
            return bool(loc.street or loc.door_no or loc.building or loc.landmark)
        if slot == "floor":
            return bool(loc.floor)
        if slot == "people":
            return t.people_count is not None
        if slot == "vulnerable":
            return bool(t.vulnerable) or self.attempts["vulnerable"] >= 1
        if slot == "vulnerable_who":
            # only needed when the caller just said "yes" without saying who
            return t.vulnerable != ["unspecified"]
        if slot == "water":
            return d.water_level is not None
        return True

    def _max_attempts(self, slot: str) -> int:
        return MAX_ATTEMPTS_BY_SLOT.get(slot, MAX_ATTEMPTS)

    def _next_action(self, e: Extraction) -> Action:
        t = self.ticket
        last = self.last_action

        # Answer to a read-back?
        if last and last.kind in ("readback", "ask_correction"):
            if e.confirmation == "yes" and not self.facts_changed:
                t.location.confirmed = True
                return Action("close")
            if self.facts_changed:
                # they gave the right details: read the new version back
                return self._readback_or_close()
            if e.confirmation == "no" or e.correction:
                # "no / that's wrong" with nothing new: ask WHAT is wrong (once), never repeat
                # the same read-back word for word
                if last.kind != "ask_correction":
                    return Action("ask_correction")
            return self._readback_or_close()

        # Not getting anywhere? A human takes over (open -> yes/no -> human).
        limit = STUCK_LIMIT_PANIC if self.panic else STUCK_LIMIT
        if self.stuck_turns >= limit:
            return Action("handoff")

        if self.turns >= settings.max_turns:
            return Action("handoff" if self.ticket.location.confidence == LocConfidence.UNKNOWN else "close")

        for slot in SLOT_ORDER:
            if not self._slot_filled(slot) and self.attempts[slot] < self._max_attempts(slot):
                self.attempts[slot] += 1
                variant = 2 if (self.panic and slot in SIMPLE_WHEN_PANIC) else self.attempts[slot]
                return Action("ask", slot=slot, attempt=variant)

        return self._readback_or_close()

    def _readback_or_close(self) -> Action:
        t = self.ticket
        nothing_to_read = not (t.people_count or t.location.locality or t.location.street
                               or t.location.landmark or t.location.door_no or t.location.building)
        if nothing_to_read:
            return Action("handoff")
        if self.readbacks >= MAX_READBACKS or (
                self.ticket.location.confidence == LocConfidence.UNKNOWN and self.readbacks >= 1):
            return Action("close")
        self.readbacks += 1
        return Action("readback")

    def _line(self, a: Action, lang: str) -> str:
        t = self.ticket
        if a.kind == "ask":
            return phrases.say(f"{a.slot}{a.attempt}", lang)
        if a.kind == "readback":
            return phrases.say("readback", lang, details=phrases.readback_details(t, lang))
        if a.kind == "ask_correction":
            return phrases.say("ask_correction", lang)
        if a.kind == "handoff":
            return phrases.say("handoff", lang, digits=spoken_digits(t.id))
        key = "close_callback" if self._needs_location_callback() else "close"
        return phrases.say(key, lang, digits=spoken_digits(t.id))

    def _say(self, a: Action, lang: str, e: Extraction, used_llm: bool, new_panic: bool) -> str:
        """Reply = [urgent | acknowledgement] + [calming line] + [answer to their question] + next line."""
        parts = []
        self.ack_status = "-"
        if a.urgent_preface:
            parts.append(phrases.say("urgent", lang))
        elif e.caller_question in ANSWERABLE:
            self.ack_status = "skipped (answering their question instead)"
        elif a.kind in ("ask", "readback", "ask_correction"):
            llm_ack = None
            if used_llm:
                llm_ack, reason = check_ack(e.ack, lang)
                self.ack_status = "llm" if llm_ack else f"rejected: {reason} ({e.ack!r})"
                if not llm_ack:
                    log.info("ack not used: %s (%r)", reason, e.ack)
            else:
                self.ack_status = "quick (fixed)"
            if llm_ack:
                parts.append(llm_ack)
            elif a.kind == "ask" and not e.unclear:
                parts.append(phrases.say("ack", lang))
        if new_panic and not self.calmed:
            parts.append(phrases.say("calm", lang))
            self.calmed = True
        if e.caller_question in ANSWERABLE:
            parts.append(phrases.say(f"ans_{e.caller_question}", lang))
        parts.append(self._line(a, lang))
        return " ".join(parts)

    def _needs_location_callback(self) -> bool:
        # Area-only or unknown is not enough for a boat to find the house,
        # even if the caller confirmed it. A human calls back first.
        return self.ticket.location.confidence in (LocConfidence.UNKNOWN, LocConfidence.AREA)

    def _hand_off(self) -> None:
        t = self.ticket
        t.call_state = CallState.HANDED_OFF
        t.status = Status.NEEDS_CALLBACK
        t.escalate_to_human = True
        reason = "caller could not give details (panic / no answers) - human officer needed"
        if reason not in t.followup_reasons:
            t.followup_reasons.append(reason)
        if "needs human: caller could not answer" not in t.priority_reasons:
            t.priority_reasons.append("needs human: caller could not answer")
        self.done = True

    def _finish(self) -> None:
        t = self.ticket
        t.call_state = CallState.COMPLETED
        if self._needs_location_callback():
            t.status = Status.NEEDS_CALLBACK
            t.followup_reasons.append(f"location precision only '{t.location.confidence.value}'")
        if not t.location.confirmed and t.location.confidence != LocConfidence.UNKNOWN \
                and "location not confirmed by caller" not in t.followup_reasons:
            t.followup_reasons.append("location not confirmed by caller")
        # Floodwater keeps rising: a "stable" P2 can become P0 within the hour. Nothing else would
        # ever look at this ticket again, so mark it for a water-level re-check call.
        if t.priority == "P2" and t.danger.water_level not in (None, "none") \
                and RECHECK_REASON not in t.followup_reasons:
            t.followup_reasons.append(RECHECK_REASON)
        self.done = True

    def _last_question(self) -> Optional[str]:
        """English version of what we just asked, as context for the extractor."""
        a = self.last_action
        if not a or a.kind in ("close", "handoff"):
            return None
        return f"{a.key}: {self._line(a, 'en-IN')}"

    def _log(self, role: str, text: str, lang: Optional[str]) -> None:
        self.ticket.transcript.append(Turn(role=role, text=text, lang=lang))

    def _result(self, reply: str, action: Optional[Action]) -> dict:
        return {
            "reply": reply,
            "reply_lang": reply_language(self.ticket.language)[0],
            "action": action.key if action else None,
            "done": self.done,
            "ticket": self.ticket.model_dump(),
        }