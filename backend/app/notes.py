"""The AI note-taker, the notes check, and the simulated caller.

1. Notes: after every caller turn (AI call or operator call), write control-room notes in English:
   a 2-line summary, details that don't fit the ticket's fields (hazards, mobility, access...),
   and an English translation of each caller line. Runs in the background: the call never waits.
   Notes are for people. They never change the ticket's priority.

2. Check: compare what an operator typed during a call with what was actually said, point by
   point, with the caller's exact words as evidence. It only reports; the operator decides.

3. Simulated caller (demo): plays a caller from a short list of facts, so an operator can talk
   freely to someone during a solo recording.

Kept in its own SQLite table, like dispatch, so the Ticket model doesn't change.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import threading
import time
from typing import Callable, Optional

from starlette.concurrency import run_in_threadpool

from .config import settings
from .language import LANG_NAMES

log = logging.getLogger("notes")

DETAIL_KINDS = ("hazard", "medical", "mobility", "access", "needs", "contact", "other")
CHECK_STATUSES = ("differs", "not_heard", "missing", "match")

NOTES_SYSTEM = """You keep the control-room notes for one call to a flood rescue phone line.
Return ONLY a JSON object: {"summary": str, "details": [{"text": str, "kind": str, "at": str}], "translations": [{"i": int, "en": str}]}
summary: at most 2 short sentences in plain English, most urgent first: who, where, water, danger. Only facts said in the call.
details: things said in the call that a rescue team needs but the ticket fields don't hold: mobility ("grandmother can't walk"),
  hazards (live wire, gas, snake, wall cracking), access (narrow lane, locked gate), contact (phone battery low), needs (insulin, food).
  kind: hazard|medical|mobility|access|needs|contact|other. Each text at most 12 words. "at" = the time it was said (mm:ss).
  Never repeat what the ticket fields already say. Never guess. Keep earlier details unless the caller corrected them.
translations: an English translation for each line listed under "Translate", by its index i. Keep names as spoken. Natural English."""

CHECK_SYSTEM = """Compare an operator's quick notes from a flood rescue call with what was actually said in the call.
Return ONLY a JSON object: {"items": [{"status": str, "topic": str, "operator": str|null, "call": str|null, "quote": str|null, "at": str|null}]}
One item per fact a rescue team needs: area, street, house or door number, floor, landmark, number of people, who is vulnerable,
water level, water rising, injuries, hazards, medical needs.
status:
  match: the notes agree with the call. Shorthand is fine ("4 ppl" = 4 people, "granny" = grandmother, "1st fl" = first floor).
  differs: the notes say something different from the call. Give both.
  missing: the caller said it and a rescue team needs it, but the notes don't have it.
  not_heard: the notes say it but nothing in the call supports it.
The transcript is the truth. Numbers spoken as words count ("बारह" = 12, "naalu" = 4). A later correction by the caller replaces the earlier version.
operator: what the notes say (null if missing). call: what the call says, in English (null if not_heard).
quote: the caller's exact words copied from the transcript, in their language (null if none). at: the time of that line (mm:ss).
topic: 1-3 plain words ("Door number", "Water level"). Never invent quotes."""

SIM_CALLER_SYSTEM = """You are role-playing a person calling a flood rescue phone line, for a training demo.
Facts about you and your situation: {facts}
Reply to the last thing the operator said, in {lang_name}{script_note}, the way a frightened but cooperative person talks on the phone:
1 or 2 short sentences. Answer what was asked; add at most one other relevant fact. Stay consistent with the facts and with what
you already said. If asked to confirm details that are right, say yes; if something is wrong, correct it. Never mention being an AI
or a simulation. Output only the words you say."""


def mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _ticket_dict(t) -> dict:
    return t.model_dump() if hasattr(t, "model_dump") else dict(t)


def ticket_facts(t: dict) -> str:
    """The ticket's structured fields, in short English, so the notes don't repeat them."""
    loc = t.get("location") or {}
    d = t.get("danger") or {}
    parts = []
    where = ", ".join(str(x) for x in (loc.get("door_no") and f"door {loc['door_no']}", loc.get("building"),
                                         loc.get("street"), loc.get("locality"),
                                         loc.get("floor") and f"floor {loc['floor']}") if x)
    if where:
        parts.append(f"location: {where}")
    if loc.get("landmark"):
        parts.append(f"landmark: {loc['landmark']}")
    if t.get("people_count"):
        parts.append(f"people: {t['people_count']}")
    if t.get("vulnerable"):
        parts.append(f"vulnerable: {', '.join(t['vulnerable'])}")
    if d.get("water_level"):
        parts.append(f"water: {d['water_level']}{', rising' if d.get('water_rising') else ''}")
    for k in ("injured", "trapped", "structure_unsafe", "medical_emergency"):
        if d.get(k) is not None:
            parts.append(f"{k}: {d[k]}")
    if t.get("medical_need"):
        parts.append(f"medical: {t['medical_need']}")
    return "; ".join(parts) or "-"


def transcript_lines(t: dict, start: Optional[float] = None) -> list[tuple[int, str, str, str, Optional[str]]]:
    """[(index, mm:ss, role, text, lang)] for the whole call, times from the first line."""
    turns = t.get("transcript") or []
    if not turns:
        return []
    t0 = start or turns[0].get("ts") or 0
    return [(i, mmss((x.get("ts") or t0) - t0), x.get("role", "?"), x.get("text", ""), x.get("lang"))
            for i, x in enumerate(turns)]


def _role_name(role: str) -> str:
    return {"caller": "Caller", "agent": "Surgeline", "operator": "Operator"}.get(role, role.title())


def fallback_summary(t: dict) -> str:
    """Notes from the ticket fields alone: used offline, or when the LLM fails."""
    loc = t.get("location") or {}
    d = t.get("danger") or {}
    who = f"{t['people_count']} people" if t.get("people_count") else "People not known yet"
    if t.get("vulnerable"):
        who += f", including {', '.join(v for v in t['vulnerable'] if v != 'unspecified') or 'someone vulnerable'}"
    where = ", ".join(x for x in (loc.get("street"), loc.get("locality")) if x) or "location not known yet"
    water = f" Water at {d['water_level']}{', rising' if d.get('water_rising') else ''}." if d.get("water_level") else ""
    return f"{who} at {where}.{water}"


class Notes:
    def __init__(self, path: str, llm, get_ticket: Callable[[str], Optional[object]]):
        self.llm = llm
        self.get_ticket = get_ticket
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("""CREATE TABLE IF NOT EXISTS call_notes (
            ticket_id TEXT PRIMARY KEY, summary TEXT, details TEXT DEFAULT '[]', translations TEXT DEFAULT '{}',
            operator_notes TEXT DEFAULT '', check_items TEXT, checked_at REAL, updated_at REAL)""")
        self._db.commit()
        self._running: set[str] = set()
        self._last_run: dict[str, float] = {}     # ticket -> when its notes last started
        self._dirty: set[str] = set()
        self._tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------ storage
    def get(self, ticket_id: str) -> dict:
        # Reads take the lock too: the note-taker writes from a background thread while the
        # dashboard reads, and one SQLite connection can't be used by two threads at once.
        with self._lock:
            row = self._db.execute("SELECT summary, details, translations, operator_notes, check_items, checked_at, updated_at "
                                   "FROM call_notes WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if not row:
            return {"summary": None, "details": [], "translations": {}, "operator_notes": "",
                    "check": None, "checked_at": None, "updated_at": None}
        return {"summary": row[0], "details": json.loads(row[1] or "[]"), "translations": json.loads(row[2] or "{}"),
                "operator_notes": row[3] or "", "check": json.loads(row[4]) if row[4] else None,
                "checked_at": row[5], "updated_at": row[6]}

    def _save(self, ticket_id: str, **fields) -> dict:
        cur = self.get(ticket_id)
        cur.update(fields)
        with self._lock:
            self._db.execute(
                "INSERT INTO call_notes (ticket_id, summary, details, translations, operator_notes, check_items, checked_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(ticket_id) DO UPDATE SET summary = excluded.summary, "
                "details = excluded.details, translations = excluded.translations, operator_notes = excluded.operator_notes, "
                "check_items = excluded.check_items, checked_at = excluded.checked_at, updated_at = excluded.updated_at",
                (ticket_id, cur["summary"], json.dumps(cur["details"], ensure_ascii=False),
                 json.dumps(cur["translations"], ensure_ascii=False), cur["operator_notes"],
                 json.dumps(cur["check"], ensure_ascii=False) if cur["check"] is not None else None,
                 cur["checked_at"], time.time()))
            self._db.commit()
        return self.get(ticket_id)

    # ------------------------------------------------------------ notes
    def schedule(self, ticket_id: str) -> None:
        """Update the notes in the background. Several calls in a row are coalesced."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.update_now(ticket_id)  # no event loop (scripts, some tests): do it inline
            return
        if ticket_id in self._running:
            self._dirty.add(ticket_id)
            return
        task = loop.create_task(self._run(ticket_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, ticket_id: str) -> None:
        self._running.add(ticket_id)
        try:
            while True:
                # At most every NOTES_MIN_GAP_SECONDS per call, and never while the LLM is rate
                # limited: the live call's extract gets the quota first.
                gap = settings.notes_min_gap_seconds - (time.time() - self._last_run.get(ticket_id, 0.0))
                wait = max(gap, getattr(self.llm, "cooldown_until", 0.0) - time.time())
                if wait > 0:
                    await asyncio.sleep(min(wait, 30.0))
                self._last_run[ticket_id] = time.time()
                self._dirty.discard(ticket_id)
                await run_in_threadpool(self.update_now, ticket_id)
                if ticket_id not in self._dirty:
                    break
        except Exception as e:  # never let a notes failure touch the call
            log.warning("notes for %s failed: %s", ticket_id, e)
        finally:
            self._running.discard(ticket_id)

    def update_now(self, ticket_id: str) -> dict:
        t = self.get_ticket(ticket_id)
        if t is None:
            return self.get(ticket_id)
        t = _ticket_dict(t)
        cur = self.get(ticket_id)
        lines = transcript_lines(t)
        to_translate = [i for i, _, role, text, lang in lines
                        if role in ("caller", "operator") and str(i) not in cur["translations"]
                        and (lang or "") != "en-IN" and text.strip()]
        try:
            out, _ = self.llm.chat_json(NOTES_SYSTEM, self._notes_prompt(t, lines, to_translate, cur),
                                        model=settings.notes_llm_model, max_tokens=settings.notes_max_tokens)
            summary = str(out.get("summary") or "").strip() or fallback_summary(t)
            details = []
            for d in out.get("details") or []:
                if isinstance(d, dict) and str(d.get("text") or "").strip():
                    kind = d.get("kind") if d.get("kind") in DETAIL_KINDS else "other"
                    details.append({"text": str(d["text"]).strip()[:120], "kind": kind, "at": str(d.get("at") or "")[:5]})
            translations = dict(cur["translations"])
            valid = set(to_translate)
            for tr in out.get("translations") or []:
                try:
                    i = int(tr.get("i"))
                except (TypeError, ValueError, AttributeError):
                    continue
                if i in valid and str(tr.get("en") or "").strip():
                    translations[str(i)] = str(tr["en"]).strip()
        except NotImplementedError:
            summary, details, translations = fallback_summary(t), cur["details"], cur["translations"]
        except Exception as e:
            log.warning("notes LLM failed for %s, keeping rule-based notes: %s", ticket_id, e)
            summary, details, translations = cur["summary"] or fallback_summary(t), cur["details"], cur["translations"]
        return self._save(ticket_id, summary=summary, details=details[:12], translations=translations)

    @staticmethod
    def _notes_prompt(t: dict, lines, to_translate, cur) -> str:
        body = "\n".join(f"[{i}] {at} {_role_name(role)}: {text}" for i, at, role, text, _ in lines[-40:])
        prev = "\n".join(f"- {d['at']} {d['text']}" for d in cur["details"]) or "-"
        return (f"Ticket fields: {ticket_facts(t)}\n"
                f"Previous summary: {cur['summary'] or '-'}\nPrevious details:\n{prev}\n"
                f"Transcript:\n{body}\n"
                f"Translate: {', '.join(map(str, to_translate)) or 'none'}")

    # ------------------------------------------------------------ check
    def check(self, ticket_id: str, operator_notes: str) -> dict:
        """Compare the operator's notes with the call. Saves both; returns the notes record."""
        t = self.get_ticket(ticket_id)
        if t is None:
            raise KeyError(ticket_id)
        t = _ticket_dict(t)
        lines = transcript_lines(t)
        body = "\n".join(f"{at} {_role_name(role)}: {text}" for _, at, role, text, _ in lines[-60:])
        try:
            out, _ = self.llm.chat_json(CHECK_SYSTEM, f"Ticket fields (may be incomplete): {ticket_facts(t)}\n"
                                                      f"Transcript:\n{body}\n\nOperator's notes:\n{operator_notes or '(empty)'}",
                                        model=settings.notes_llm_model)
            items = clean_check_items(out.get("items"), {text for _, _, _, text, _ in lines})
        except NotImplementedError:
            items = rule_check(t, operator_notes)
        except Exception as e:
            log.warning("notes check LLM failed for %s, using rule check: %s", ticket_id, e)
            items = rule_check(t, operator_notes)
        return self._save(ticket_id, operator_notes=operator_notes, check=items, checked_at=time.time())

    def save_operator_notes(self, ticket_id: str, operator_notes: str) -> dict:
        return self._save(ticket_id, operator_notes=operator_notes)

    # ------------------------------------------------------------ simulated caller
    def caller_reply(self, ticket_id: str, facts: str, lang: str) -> Optional[str]:
        """What the simulated caller says next, or None if the LLM isn't available."""
        t = self.get_ticket(ticket_id)
        t = _ticket_dict(t) if t is not None else {"transcript": []}
        lang_name = LANG_NAMES.get(lang, "English")
        script_note = "" if lang == "en-IN" else f", in {lang_name} script"
        body = "\n".join(f"{_role_name(role)}: {text}" for _, _, role, text, _ in transcript_lines(t)[-20:]) or "(the call just connected)"
        try:
            reply = self.llm.chat_text(SIM_CALLER_SYSTEM.format(facts=facts, lang_name=lang_name, script_note=script_note),
                                       f"The call so far:\n{body}\n\nYour reply:", model=settings.notes_llm_model)
        except NotImplementedError:
            return None
        except Exception as e:
            log.warning("simulated caller failed: %s", e)
            return None
        reply = re.sub(r"^(caller|me|you)\s*:\s*", "", reply.strip(), flags=re.I).strip()
        return reply[:300] or None


def clean_check_items(items, transcript_texts: set[str]) -> list[dict]:
    """Keep only well-formed items; drop quotes that aren't in the transcript; most important first."""
    out = []
    for it in items or []:
        if not isinstance(it, dict) or it.get("status") not in CHECK_STATUSES:
            continue
        quote = it.get("quote")
        if quote and not any(str(quote).strip(" “”\"'") in text for text in transcript_texts):
            quote = None  # never show words the caller didn't say
        out.append({"status": it["status"], "topic": str(it.get("topic") or "Detail")[:40],
                    "operator": it.get("operator") or None, "call": it.get("call") or None,
                    "quote": quote, "at": (str(it["at"])[:5] if it.get("at") else None)})
    order = {s: i for i, s in enumerate(CHECK_STATUSES)}
    return sorted(out, key=lambda x: order[x["status"]])


_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def rule_check(t: dict, notes: str) -> list[dict]:
    """Offline check: the ticket's main fields against the notes, by plain matching."""
    n = (notes or "").lower()
    nums = {int(x) for x in re.findall(r"\b\d+\b", n)} | {v for k, v in _NUM.items() if re.search(rf"\b{k}\b", n)}
    loc, d = t.get("location") or {}, t.get("danger") or {}
    items = []

    def add(topic, value, present, wrong=None):
        if value in (None, "", []):
            return
        if present:
            items.append({"status": "match", "topic": topic, "operator": str(value), "call": str(value), "quote": None, "at": None})
        elif wrong is not None:
            items.append({"status": "differs", "topic": topic, "operator": str(wrong), "call": str(value), "quote": None, "at": None})
        else:
            items.append({"status": "missing", "topic": topic, "operator": None, "call": str(value), "quote": None, "at": None})

    add("Area", loc.get("locality"), bool(loc.get("locality")) and loc["locality"].lower() in n)
    add("Street", loc.get("street"), bool(loc.get("street")) and loc["street"].split()[0].lower() in n)
    if loc.get("door_no"):
        door = re.search(r"(?:door|house|no\.?|#)\s*(\d+)", n)
        add("Door number", loc["door_no"], str(loc["door_no"]) in re.findall(r"\d+", n) and (not door or door.group(1) == str(loc["door_no"])),
            wrong=door.group(1) if door and door.group(1) != str(loc["door_no"]) else None)
    if t.get("people_count"):
        ppl = re.search(r"(\d+)\s*(?:ppl|people|persons|members|of us)", n)
        add("People", t["people_count"], t["people_count"] in nums and (not ppl or int(ppl.group(1)) == t["people_count"]),
            wrong=ppl.group(1) if ppl and int(ppl.group(1)) != t["people_count"] else None)
    if d.get("water_level"):
        levels = ["ankle", "knee", "waist", "chest", "neck", "roof"]
        said = next((lv for lv in levels if lv in n), None)
        add("Water level", d["water_level"], said == d["water_level"], wrong=said if said and said != d["water_level"] else None)
    order = {s: i for i, s in enumerate(CHECK_STATUSES)}
    return sorted(items, key=lambda x: order[x["status"]])