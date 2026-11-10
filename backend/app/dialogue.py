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
import re
import time
from dataclasses import dataclass
from typing import Optional

from . import geocode, phrases, prompts
from .config import settings
from .dispatch import HUMAN_OPERATORS, HUMAN_OPERATORS_BUSY
from .gazetteer import match_locality, resolve
from .intents import ANGER, ASK_ROBOT, REFUSE_AI, REQUEST_HUMAN, STATUS_QUERY, detect as detect_intents
from .language import LanguageTracker, detect_script_language, judge_turn, reply_language
from .llm import LLM
from .models import CallState, Extraction, LocConfidence, Status, Ticket, Turn
from .priority import assess
from .quick_parse import quick_parse
from .safety_net import facts_by_rule
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
                 "o'clock", "बजे", "மணிக்கு", "மணிக்குள்", "గంటలకు", "గంటల్లో"]
# "5 pm", "10:30 am" (but not "I am here")
CLOCK_TIME = re.compile(r"\b\d{1,2}(:\d{2})?\s?(am|pm|a\.m\.|p\.m\.)(?![a-z])")


def sounds_like_promise(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in PROMISE_WORDS) or bool(CLOCK_TIME.search(low))


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
    if sounds_like_promise(a):
        return None, "sounds like a promise"
    return (a if a[-1] in ".!।" else a + ("।" if lang == "hi-IN" else ".")), "ok"


def check_reply(reply: Optional[str], lang: str) -> tuple[Optional[str], str]:
    """The LLM's reply to something off-script: one short sentence, in the call's language and
    script, no promise or time. May be a question ("Yes, tell me the pin code?")."""
    if not reply:
        return None, "missing"
    r = " ".join(reply.split())
    if len(r.split()) > 14 or len(r) > 110:
        return None, "too long"
    if detect_script_language(r) != lang:
        return None, f"wrong language ({detect_script_language(r)})"
    if sounds_like_promise(r):
        return None, "sounds like a promise"
    return (r if r[-1] in ".!?।" else r + ("।" if lang == "hi-IN" else ".")), "ok"


def safe_ack(ack: Optional[str], lang: str) -> Optional[str]:
    return check_ack(ack, lang)[0]


@dataclass
class Action:
    kind: str                 # ask | go_ahead | reply | readback | ask_correction | close | handoff | wait
    slot: Optional[str] = None
    attempt: int = 1
    urgent_preface: bool = False
    rephrased: bool = False   # the caller didn't understand: same question, simpler words
    text: Optional[str] = None  # kind "reply": the checked LLM reply to speak

    @property
    def key(self) -> str:
        return f"ask:{self.slot}" if self.kind == "ask" else self.kind


# "Shall I tell you?" in the four languages, in their scripts and in English letters. Checked by
# rule because the LLM misses some wordings ("చెప్పమంటావా?" when it only knows "చెప్పనా?").
# After a plain answer: "Okay." / "Got it." / "Yes, noted.", in turn.
ACKS = ("ack", "ack2", "ack3")


def names_place_or_number(e: Extraction) -> bool:
    """Did this turn give part of an address, or how many people there are?"""
    return any(v is not None and v != "" for v in (e.locality, e.street, e.door_no, e.building, e.landmark,
                                                   e.floor, e.pincode, e.people_count))


WRONG_DETAILS_REASON = "caller says the details are wrong but could not say what - officer to confirm"

OFFER_TO_TELL = [
    # English
    "shall i tell", "should i tell", "can i tell", "may i tell", "shall i say", "should i say",
    "shall i explain", "should i explain", "do you want me to tell", "want me to tell", "let me tell",
    # Hindi
    "बताऊँ", "बताऊं", "बता दूँ", "बता दूं", "बतायें", "बताएँ", "बोलूँ", "बोलूं",
    "bataun", "bataoon", "bata doon", "bata du", "bolun", "boloon",
    # Telugu
    "చెప్పనా", "చెప్పమంటావా", "చెప్పమంటారా", "చెప్పాలా", "చెప్పేదా", "చెప్తాను", "చెప్పొచ్చా",
    "cheppana", "cheppamantava", "cheppamantara", "cheppala",
    # Tamil
    "சொல்லட்டுமா", "சொல்லவா", "சொல்லணுமா", "சொல்றேன்", "sollatuma", "sollattuma", "sollava",
]


def offers_to_tell(text: str) -> bool:
    t = " ".join(text.lower().split())
    return any(p in t for p in OFFER_TO_TELL)


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


OFF_MAP_REASON = "area not on the map list: find it by hand"


def apply_extraction(t: Ticket, e: Extraction) -> None:
    loc = t.location
    location_changed = False
    if e.pincode and loc.pincode != e.pincode:
        loc.pincode = e.pincode
        location_changed = True
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
        if loc.locality and loc.lat is None and OFF_MAP_REASON not in t.followup_reasons:
            t.followup_reasons.append(OFF_MAP_REASON)   # e.g. "Sainikpuri": not in the demo list

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
        self.last_parts: list[str] = []        # the last reply, split into its spoken parts (voice caches each)
        self.lang_check: dict = {}             # how the last turn's language was judged (for debugging)
        self.area_unknown = False              # caller said they don't know where they are
        self.go_aheads = 0                     # "shall I tell you?" -> "yes, tell me" (at most twice)
        self.replies = 0                       # LLM-written replies to off-script turns (at most 3 a call)
        self.last_reply: Optional[str] = None  # what we said in the last such reply (context for the next turn)
        self.asked: set[str] = set()           # question wordings already used ("area3", "street1"...)
        # The waiting room (design v2, section 5): once the AI's questions are done for a P0/P1 case,
        # or the caller wants a human, the line stays open and the caller waits in line for an
        # officer. The AI stops asking, keeps listening and filling the ticket, and reassures.
        self.waiting = False
        self.human_requests = 0                # "let me talk to a person": first -> told an officer will speak, questions go on
        self.handoff_reason: Optional[str] = None  # why the next handover happens, if not the usual reason
        self.calm_pending = False              # the calming line, held back a turn (see _say)
        self.acks_said = 0                     # fixed acknowledgements said so far (they take turns)
        self.relief_said = False               # "thank goodness everyone is all right" (once a call)
        self.told_still_in_line = False        # said "you're still in line" since waiting began
        self.unclear_turns = 0                 # consecutive turns we couldn't understand
        self.one_person_said = False           # "give the phone to one person" (once a call)
        self.placed_area = None                # the area/PIN we last placed on the map (geocode.area_key)
        self.place_in_turn = False             # voice calls look the area up while the reply is spoken
        self.area_to_place = False             # ...and this says there's one to look up this turn
        self.prefix: list[str] = []            # phrase keys said before this turn's line
        self.turn_intents: set[str] = set()

    # ------------------------------------------------------------------ public
    def greeting(self) -> str:
        text = prompts.GREETING["text"]
        self._log("agent", text, prompts.GREETING["lang"])
        # The greeting ends with a danger question, so the first answer is read as its answer
        # ("nahi" = nobody in danger). It doesn't use up one of the danger question's two tries:
        # callers answer a greeting by describing what happened, and danger decides P0.
        self.last_action = Action("ask", slot="danger", attempt=1)
        self.store.save(self.ticket)
        return text

    def handle(self, text: str, detected_lang: Optional[str] = None) -> dict:
        if self.done:
            return self._result("", None)
        started = time.perf_counter()
        t = self.ticket
        self.turns += 1

        # The ack is written in the call's language so far (or, on the first turn, the one
        # speech-to-text heard). If this turn switches language, a wrong-language ack is dropped.
        tentative = self.lang.current if self.lang.locked else (detected_lang or detect_script_language(text))

        # Understand the reply: quick parse first, LLM only if needed
        last_key = self.last_action.key if self.last_action else None
        extraction = quick_parse(text, last_key)
        used_llm = extraction is None
        if used_llm:
            extraction = self.llm.extract(text, self._last_question(),
                                          known_summary(t, reply_language(tentative)[0]))
            self.llm_calls += 1
            self.tokens += extraction.tokens_used
            if extraction.llm_failed:
                # The LLM call failed (rate limit, timeout): keep the plainest danger facts by rule,
                # so "nobody hurt, water rising" or "we are four" isn't lost and asked again.
                rule = facts_by_rule(text, self.last_action.slot if self.last_action else None)
                if rule:
                    extraction = extraction.model_copy(update={**rule, "unclear": False})

        # Language: decided after the LLM has read the words, so a wrong speech-to-text guess
        # (Hindi written in Tamil letters) can't switch the call on its own.
        heard, sure = judge_turn(detected_lang, text, extraction.spoken_language, extraction.llm_failed)
        if self.lang.locked and extraction.unclear and not extraction.llm_failed:
            # A line we couldn't understand ("Hello.", "Can I do?" from a breaking-up line) says
            # nothing reliable about the language either: it can't switch the call.
            call_lang = self.lang.current
        else:
            call_lang = self.lang.update(heard, text, sure)
        reply_lang, needs_interpreter = reply_language(call_lang)
        t.language = call_lang
        t.needs_interpreter = t.needs_interpreter or needs_interpreter
        self._log("caller", text, heard)
        self.lang_check = {"stt": detected_lang, "llm": extraction.spoken_language,
                           "heard": heard, "sure": sure, "call": call_lang,
                           "llm_failed": extraction.llm_failed}
        before = facts_snapshot(t)
        apply_extraction(t, extraction)
        self._place_off_map_area()
        if "rescue" not in t.needs and (t.danger.trapped or t.danger.water_level in
                                        ("knee", "waist", "chest", "neck", "roof")):
            t.needs.append("rescue")

        was_escalated = t.escalate_to_human
        t.priority, t.priority_reasons, alert = assess(t)
        intents = detect_intents(text)
        if extraction.asks_for_human and REFUSE_AI not in intents:
            intents.add(REQUEST_HUMAN)
        self.turn_intents = intents
        if intents & {REQUEST_HUMAN, REFUSE_AI}:
            reason = "caller declined the AI" if REFUSE_AI in intents else "caller asked for a person"
            if reason not in t.followup_reasons:
                t.followup_reasons.append(reason)
        if STATUS_QUERY in intents:
            # one answer for every status question ("kab aayegi?", "any update?")
            extraction.caller_question = "when_help"
        t.escalate_to_human = was_escalated or alert

        new_panic = extraction.panic == "high" and not self.panic
        self.panic = self.panic or extraction.panic == "high"

        # Did this turn actually change a fact? (The LLM's `correction` flag alone isn't enough:
        # "nahi galat he" says something is wrong but gives no new details.)
        self.facts_changed = facts_snapshot(t) != before

        # "Shall I tell you?" with nothing else new in it: say "yes, tell me" (see _next_action).
        if (extraction.caller_question in (None, "other") and not self.facts_changed
                and offers_to_tell(text)):
            extraction.caller_question = "go_ahead"

        # Asking us something shows the caller is engaged, but only the FIRST time:
        # "boat kab aayegi?" asked again and again is a caller who is stuck.
        new_question = ((extraction.caller_question in ANSWERABLE | {"rephrase", "go_ahead"} or bool(extraction.reply))
                        and extraction.caller_question not in self.questions_seen)
        for intent in intents & {REQUEST_HUMAN, ASK_ROBOT}:
            new_question = new_question or intent not in self.questions_seen
            self.questions_seen.add(intent)
        if extraction.dont_know and self.last_action and self.last_action.slot == "area":
            self.area_unknown = True
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
        # A failed LLM call (rate limit, timeout) is our problem, not the caller's: it never counts.
        if progressed or self.waiting:
            self.stuck_turns = 0
        elif self.last_action is not None and not extraction.llm_failed:
            self.stuck_turns += 1

        # Bad audio (design v2, 8.4): a second turn in a row we couldn't understand ->
        # "give the phone to one person" before any handover.
        # (a failed LLM call or an offer like "shall I tell you?" is not bad audio)
        not_understood = (extraction.unclear and not extraction.llm_failed and not self.facts_changed
                          and not extraction.caller_question and not intents)
        self.unclear_turns = self.unclear_turns + 1 if not_understood else 0
        self.prefix = []
        one_person = self.unclear_turns >= 2 and not self.one_person_said and not self.waiting

        if self.waiting:
            action = self._waiting_action(intents, t.escalate_to_human and not was_escalated)
        else:
            action = self._intent_action(intents)
            if action is None:
                if one_person:
                    self.one_person_said = True
                    self.prefix.append("one_person")   # this turn: the ladder's next step, not a handover
                action = self._next_action(extraction)
        action.urgent_preface = t.escalate_to_human and not was_escalated
        if action.kind == "ask":
            self.asked.add(f"{action.slot}{action.attempt}")

        if action.kind in ("go_ahead", "reply", "wait"):
            self.turns -= 1      # "yes, tell me" and waiting don't use up the call's question turns
        if action.kind == "wait":
            reply = " ".join(self.last_parts)
        else:
            reply = self._say(action, reply_lang, extraction, used_llm, new_panic)
        if action.kind == "close":
            if self._stays_on_line():
                self._finish(waiting=True)
            else:
                self._finish()
        elif action.kind == "handoff":
            self._hand_off()
        if action.kind in ("go_ahead", "reply", "wait"):
            # after "yes, tell me" the caller's answer is still to the question before it
            # (and while waiting in line, the last real question stays the context)
            self.last_reply = reply or None
        else:
            self.last_action = action
            self.last_reply = None
        self._log("agent", reply, reply_lang)
        self.store.save(t)

        result = self._result(reply, action)
        result["turn_ms"] = round((time.perf_counter() - started) * 1000)
        result["used_llm"] = used_llm
        result["ack_status"] = self.ack_status
        result["lang_check"] = self.lang_check
        # what the turn was understood as (for debugging a reply that looks wrong)
        result["understood"] = {"caller_question": extraction.caller_question, "dont_know": extraction.dont_know,
                                "panic": extraction.panic, "unclear": extraction.unclear,
                                "llm_failed": extraction.llm_failed}
        result["llm_calls_total"] = self.llm_calls
        result["tokens_total"] = self.tokens
        return result

    def drop(self) -> Ticket:
        """Network cut mid-call: keep everything we have, flag for callback."""
        t = self.ticket
        if not self.done:
            t.call_state = CallState.DROPPED
            t.status = Status.NEEDS_CALLBACK
            t.followup_reasons.append("hung up while waiting for an officer: call back" if self.waiting
                                      else "call dropped mid-conversation")
            self.done = True
            self.store.save(t)
        return t

    # ----------------------------------------------------------------- private
    def _place_off_map_area(self) -> None:
        """An area not on our list ("Sainikpuri", a PIN code): look it up on OpenStreetMap in the
        background, so the ticket gets a pin on the map. The caller doesn't wait for it."""
        if not settings.geocode_enabled:
            return
        t, loc = self.ticket, self.ticket.location
        key = geocode.area_key(loc)
        if key is None or key == self.placed_area:
            return
        if self.placed_area is not None and match_locality(loc.locality) is None:
            # the caller changed the area: the old pin is wrong now
            loc.lat = loc.lon = None
            if geocode.FOUND_REASON in t.followup_reasons:
                t.followup_reasons.remove(geocode.FOUND_REASON)
            if loc.locality and OFF_MAP_REASON not in t.followup_reasons:
                t.followup_reasons.append(OFF_MAP_REASON)
        self.placed_area = key
        if loc.lat is None:
            if self.place_in_turn:
                self.area_to_place = True      # voice_turn does it alongside the reply's speech
            else:
                geocode.place_in_background(t, self.store, OFF_MAP_REASON)

    def place_area(self) -> bool:
        """Look up the area found this turn (see _place_off_map_area). Blocking: run off the event loop."""
        if not self.area_to_place:
            return False
        self.area_to_place = False
        return geocode.place(self.ticket, self.store, OFF_MAP_REASON)

    def _slot_filled(self, slot: str) -> bool:
        t = self.ticket
        d = t.danger
        loc = t.location
        if slot == "danger":
            return any(v is not None for v in (d.injured, d.medical_emergency, d.water_rising,
                                                d.structure_unsafe, d.trapped)) or d.water_level is not None
        if slot == "area":
            # a named area answers "where?", on our map or not (an operator places the rest)
            return loc.locality is not None or bool(loc.pincode)
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
            if last.kind == "ask_correction":
                # We asked what is wrong and still got nothing we can use. Reading the same
                # sentence back again helps nobody: an officer sorts it out with the caller.
                self.handoff_reason = WRONG_DETAILS_REASON
                return Action("handoff")
            return self._readback_or_close()

        # Not getting anywhere? A human takes over (open -> yes/no -> human).
        limit = STUCK_LIMIT_PANIC if self.panic else STUCK_LIMIT
        if self.stuck_turns >= limit and "one_person" not in self.prefix:
            return Action("handoff")

        if self.turns >= settings.max_turns:
            return Action("handoff" if self.ticket.location.confidence == LocConfidence.UNKNOWN else "close")

        # Something the fixed flow doesn't cover ("I only know the pin code, is that ok?"): the LLM's
        # short reply, if it passes the checks. The caller's next answer is still to the same question.
        if (last and last.kind == "ask" and e.reply and not self.facts_changed and self.replies < 3
                and e.caller_question not in ANSWERABLE and e.caller_question != "rephrase"
                and e.confirmation is None):
            text, reason = check_reply(e.reply, reply_language(self.ticket.language)[0])
            if text:
                self.replies += 1
                return Action("reply", slot=last.slot, attempt=last.attempt, text=text)
            log.info("LLM reply not used: %s (%r)", reason, e.reply)

        # "Shall I tell you?": "Yes, tell me", and wait. Their next answer is still to the same question.
        if e.caller_question == "go_ahead" and last and last.kind == "ask" and self.go_aheads < 2:
            self.go_aheads += 1
            return Action("go_ahead", slot=last.slot, attempt=last.attempt)

        # "What does floor mean?": the same question again, in its simpler wording (once per question).
        if (e.caller_question == "rephrase" and last and last.kind == "ask" and not last.rephrased
                and not self._slot_filled(last.slot) and phrases.has(f"{last.slot}{last.attempt + 1}", "en-IN")):
            self.attempts[last.slot] += 1
            return Action("ask", slot=last.slot, attempt=last.attempt + 1, rephrased=True)

        for slot in SLOT_ORDER:
            if (slot == "street" and self.area_unknown and not self._slot_filled("area")
                    and not self._slot_filled("street")):
                # They don't know their area: asking for street and house number makes no sense.
                # Ask once what they can SEE nearby (unless already asked), then move on.
                self.attempts["street"] = self._max_attempts("street")
                if "area3" not in self.asked:
                    return Action("ask", slot="area", attempt=3)
                continue
            if not self._slot_filled(slot) and self.attempts[slot] < self._max_attempts(slot):
                self.attempts[slot] += 1
                if self.panic and slot in SIMPLE_WHEN_PANIC:
                    # simple version first; asked again, a different (even simpler) wording, never the same words
                    variant = 2 if self.attempts[slot] == 1 else 3
                else:
                    variant = self.attempts[slot]
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
            key = f"{a.slot}{a.attempt}"
            if phrases.has(key, lang):
                return phrases.say(key, lang)
            # no third wording for this question: soften the repeat instead of saying the same words cold
            return f'{phrases.say("again", lang)} {phrases.say(f"{a.slot}2", lang)}'
        if a.kind == "go_ahead":
            return phrases.say("go_ahead", lang)
        if a.kind == "reply":
            return a.text
        if a.kind == "readback":
            return phrases.say("readback", lang, details=phrases.readback_details(t, lang))
        if a.kind == "ask_correction":
            return phrases.say("ask_correction", lang)
        if a.kind == "handoff":
            return phrases.say("handoff", lang, digits=spoken_digits(t.id))
        if self._stays_on_line():
            # honest per priority (design v2, 5.3): P0 = an officer is alerted now; P1 = an officer
            # will speak to you, stay or hang up and keep your place. Neither ends the call.
            key = "p0_wait" if t.priority == "P0" else "p1_wait"
            return phrases.say(key, lang, digits=spoken_digits(t.id))
        key = "close_callback" if self._needs_location_callback() else "close"
        return phrases.say(key, lang, digits=spoken_digits(t.id))

    def _say(self, a: Action, lang: str, e: Extraction, used_llm: bool, new_panic: bool) -> str:
        """Reply = [urgent | acknowledgement] + [calming line] + [answer to their question] + next line."""
        parts = []
        self.ack_status = "-"
        if a.urgent_preface:
            parts.append(phrases.say("urgent", lang))
        elif self.turn_intents & {REQUEST_HUMAN, ASK_ROBOT}:
            # "I want a person" / "are you a robot?": the fixed reply answers it; an ack would echo
            # the request back ("talk to a person, okay")
            self.ack_status = "skipped (request answered by a fixed line)"
        elif ANGER in self.turn_intents:
            # shouting is distress, not abuse: one line, then straight on (never "please calm down")
            parts.append(phrases.say("anger_ack", lang))
            self.ack_status = "skipped (anger: anger_ack)"
        elif e.caller_question in ANSWERABLE:
            self.ack_status = "skipped (answering their question instead)"
        elif e.caller_question:
            # they asked something ("what does floor mean?"): an ack would echo the question
            # back as if it were an answer ("what does floor mean, understood")
            self.ack_status = "skipped (caller asked a question)"
        elif a.kind in ("ask", "readback", "ask_correction"):
            llm_ack = None
            if used_llm:
                llm_ack, reason = check_ack(e.ack, lang)
                self.ack_status = "llm" if llm_ack else f"rejected: {reason} ({e.ack!r})"
                if not llm_ack:
                    log.info("ack not used: %s (%r)", reason, e.ack)
            else:
                self.ack_status = "quick (fixed)"
            if a.kind == "ask" and self._relief_fits(e):
                # "Thank goodness everyone is all right": once, and only when it is true
                parts.append(phrases.say("relief", lang))
                self.relief_said = True
                self.ack_status = "relief"
            elif llm_ack and names_place_or_number(e):
                # Repeating a detail back is worth it for an address or a number (the caller hears
                # we got it right). Doing it on every turn is what made the agent sound like a machine.
                parts.append(llm_ack)
            elif a.kind == "ask" and not e.unclear and not self.panic:
                # (a bare "Okay." after "we are going to die" is worse than saying nothing)
                if llm_ack:
                    self.ack_status = "fixed (the turn had no address or number to repeat)"
                parts.append(phrases.say(ACKS[self.acks_said % len(ACKS)], lang))
                self.acks_said += 1
        if (new_panic or self.calm_pending) and not self.calmed:
            if (a.urgent_preface or e.caller_question in ANSWERABLE
                    or (self.calm_pending and not new_panic and a.kind != "ask")):
                # "Your case is most urgent, an officer is being alerted" (or the answer to what
                # they just asked) is what this turn says. With the calming line too, the caller
                # would hear four or five sentences before the question, so it waits for the next
                # plain question we ask.
                self.calm_pending = True
            else:
                parts.append(phrases.say("calm", lang))
                self.calmed, self.calm_pending = True, False
        if e.caller_question == "when_help":
            parts.append(phrases.say("status_deflect", lang))   # no time, no promise
        elif e.caller_question in ANSWERABLE:
            parts.append(phrases.say(f"ans_{e.caller_question}", lang))
        parts.extend(phrases.say(k, lang) for k in self.prefix)
        if a.rephrased:
            parts.append(phrases.say("rephrase", lang))
        parts.append(self._line(a, lang))
        self.last_parts = parts
        return " ".join(parts)

    def _relief_fits(self, e: Extraction) -> bool:
        """The caller just said nobody is hurt, and nothing else about the case is worrying."""
        t, d = self.ticket, self.ticket.danger
        return (not self.relief_said and e.injured is False and not self.panic
                and t.priority != "P0" and not t.escalate_to_human and not t.vulnerable and not t.medical_need
                and d.water_rising is not True and not d.trapped and not d.medical_emergency
                and not d.structure_unsafe and d.water_level not in ("waist", "chest", "neck", "roof"))

    def _needs_location_callback(self) -> bool:
        # Area-only or unknown is not enough for a boat to find the house,
        # even if the caller confirmed it. A human calls back first.
        return self.ticket.location.confidence in (LocConfidence.UNKNOWN, LocConfidence.AREA)

    def _hand_off(self) -> None:
        t = self.ticket
        t.call_state = CallState.HANDED_OFF
        t.status = Status.NEEDS_CALLBACK
        t.escalate_to_human = True
        reason = self.handoff_reason or "caller could not give details (panic / no answers) - human officer needed"
        self.handoff_reason = None
        if reason not in t.followup_reasons:
            t.followup_reasons.append(reason)
        if "needs human: caller could not answer" not in t.priority_reasons:
            t.priority_reasons.append("needs human: caller could not answer")
        self._start_waiting()

    def _stays_on_line(self) -> bool:
        """P0 and P1 callers stay on the line for an officer; P2 and P3 are reviewed, not called.
        A caller who asked for a person was told an officer will speak to them, so they stay too."""
        return (self.ticket.priority in ("P0", "P1") or self.ticket.escalate_to_human
                or self.human_requests > 0)

    def _start_waiting(self) -> None:
        t = self.ticket
        self.waiting = True
        if "waiting on the line for an officer" not in t.followup_reasons:
            t.followup_reasons.append("waiting on the line for an officer")

    def _intent_action(self, intents: set[str]) -> Optional[Action]:
        """Requests for a person, robot and status questions, anger (design v2, 5.4 and 7.4).
        Returns an action that replaces the next question, or None (prefix lines may be queued)."""
        if REFUSE_AI in intents or (REQUEST_HUMAN in intents and self.human_requests >= 1):
            # refused the machine, or asked twice: stop asking, keep them in line
            self.human_requests += 1
            self._start_waiting()
            self.told_still_in_line = True
            return self._wait_with(["ack", "still_in_line"])
        if REQUEST_HUMAN in intents:
            self.human_requests += 1
            if HUMAN_OPERATORS_BUSY < HUMAN_OPERATORS:
                return Action("handoff")      # someone is free: pass the call on now
            self.prefix.append("request_human_ack")   # then the most important missing question
        if ASK_ROBOT in intents:
            self.prefix.append("yes_automated")
        return None

    def _waiting_action(self, intents: set[str], newly_urgent: bool) -> Action:
        """A caller turn while they wait for an officer: keep filling the ticket, ask nothing.
        Say only what this turn needs; often nothing."""
        keys = []
        if newly_urgent:
            keys.append("urgent")
        if STATUS_QUERY in intents:
            keys.append("status_deflect")
        if ASK_ROBOT in intents:
            keys.append("yes_automated")
        elif intents & {REQUEST_HUMAN, REFUSE_AI}:
            keys.append("still_in_line")
        elif self.facts_changed and not newly_urgent:
            keys.append("noted")
        elif not keys and not self.told_still_in_line:
            # their first "ok" / "hello?" while waiting: say they are still in line, so the line
            # doesn't sound dead. After that, silence; the 40 s reassurance covers them.
            keys.append("still_in_line")
        if "still_in_line" in keys:
            self.told_still_in_line = True
        return self._wait_with(keys)

    def _wait_with(self, keys: list[str]) -> Action:
        lang = reply_language(self.ticket.language)[0]
        self.last_parts = [phrases.say(k, lang) for k in keys]
        return Action("wait")

    def _finish(self, waiting: bool = False) -> None:
        t = self.ticket
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
        if waiting:
            # the AI's questions are done; the caller stays on the line for an officer
            self._start_waiting()
            return
        t.call_state = CallState.COMPLETED
        self.done = True

    def question_en(self) -> Optional[str]:
        """What we just asked, in English. The speech-to-text context: it tells Prisma what the
        caller is answering without pushing it toward the call's language or script."""
        a = self.last_action
        if not a or a.kind in ("close", "handoff"):
            return None
        return self._line(a, "en-IN")

    def _last_question(self) -> Optional[str]:
        """English version of what we just asked, as context for the extractor."""
        a = self.last_action
        if not a or a.kind in ("close", "handoff"):
            return None
        asked = f"{a.key}: {self._line(a, 'en-IN')}"
        # after an off-script reply ("yes, tell me the pin code"), the LLM needs to know we said it
        return f"{asked} (then the agent said: {self.last_reply})" if self.last_reply else asked

    def _log(self, role: str, text: str, lang: Optional[str]) -> None:
        self.ticket.transcript.append(Turn(role=role, text=text, lang=lang))

    def _result(self, reply: str, action: Optional[Action]) -> dict:
        return {
            "reply": reply,
            # Same text as `reply`, split into parts. Fixed parts ("Okay.", the next question) are
            # identical every call, so voice mode can cache their audio separately from the
            # parts that change (LLM acknowledgement, read-back).
            "reply_parts": list(self.last_parts) if action else [],
            "reply_lang": reply_language(self.ticket.language)[0],
            "action": action.key if action else None,
            "done": self.done,
            # the caller is in line for an officer: keep the line open, reassure every ~40 s
            "waiting": self.waiting,
            "reassure": phrases.say("still_in_line", reply_language(self.ticket.language)[0]) if self.waiting else None,
            "ticket": self.ticket.model_dump(),
        }