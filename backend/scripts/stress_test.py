"""Stress-test Surgeline's judgement with simulated callers.

An LLM plays a caller from a fact sheet (scripts/stress_scenarios.py): panicking, switching language,
only knowing a PIN code, asking for a person, angry, not understanding a word. Surgeline answers each
line exactly as on a real call. At the end the ticket is scored against the fact sheet, every reply
is checked for known faults, and every transcript is saved so you can read the calls.

Run from flood-sos/backend with the venv active:

    python scripts\\stress_test.py                       # text mode: all scenarios (Groq only, no Gnani)
    python scripts\\stress_test.py --only telugu_panic_chest,hindi_angry
    python scripts\\stress_test.py --mode voice          # the caller is spoken by Gnani and heard by Prisma
    python scripts\\stress_test.py --mode voice --phone --noise clean,10,5
    python scripts\\stress_test.py --repeat 3            # each scenario 3 times (the caller varies)

Text mode tests the AI's judgement: the caller's words reach Surgeline exactly. Voice mode tests the
whole chain, including Prisma mishearing. Gnani's voice heard by Gnani's recogniser is the easy case:
voice results flatter real callers, even with --phone and --noise. Report them as synthetic.

Results go to stress_results/<date-time>/: report.md (scores and faults), one transcript per call
in calls/, and results.json.
"""
import argparse
import asyncio
import io
import json
import math
import random
import struct
import sys
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so "app" imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))          # so "stress_scenarios" imports

from app import phrases  # noqa: E402
from app.config import settings  # noqa: E402
from app.dialogue import CallSession, sounds_like_promise  # noqa: E402
from app.language import LANG_NAMES, detect_script_language  # noqa: E402
from app.models import Ticket  # noqa: E402
from stress_scenarios import SCENARIOS  # noqa: E402

MAX_CALLER_TURNS = 16
TURNS_AFTER_WAITING = 2          # once in line for an officer, the caller says this many more things

CALLER_SYSTEM = """You are role-playing a person calling a flood rescue phone line, to test the line. Stay in character.
What is true about you and your situation: {facts}
How you behave on this call: {behaviour}
This turn, speak {lang_desc}.{switch_note}
Talk the way people really talk on the phone: everyday words, mixing in common English words where that is natural.
1 or 2 short sentences. Answer what the agent just said or asked, following your behaviour notes. Never invent facts
beyond the ones given; if asked something they don't cover, say you don't know. If the agent read your details back
and they are right, say yes. Never mention being an AI or a test. Output only the words you say."""

LANG_DESC = {
    "hi-IN": "Hindi, in Devanagari script",
    "te-IN": "Telugu, in Telugu script",
    "ta-IN": "Tamil, in Tamil script",
    "en-IN": "English (Indian English)",
    "hi-IN-latn": "Hindi mixed with English, written in English letters (Hinglish)",
}


# ------------------------------------------------------------------------------- the caller

def lang_at(scenario: dict, turn: int) -> str:
    code = scenario["langs"][0][1]
    for start, c in scenario["langs"]:
        if turn >= start:
            code = c
    return code


def stt_tag(code: str) -> str:
    """The language tag a correct speech recogniser would give."""
    return "hi-IN" if code == "hi-IN-latn" else code


class LLMCaller:
    """The simulated caller: an LLM playing the scenario, one line per turn."""

    def __init__(self, llm, pause: float):
        self.llm, self.pause = llm, pause

    def say(self, scenario: dict, turn: int, transcript: list[dict]) -> str:
        code = lang_at(scenario, turn)
        switched = turn > 1 and code != lang_at(scenario, turn - 1)
        system = CALLER_SYSTEM.format(
            facts=scenario["facts"], behaviour=scenario["behaviour"], lang_desc=LANG_DESC[code],
            switch_note=" You have just switched to this language (see your behaviour notes)." if switched else "")
        body = "\n".join(f"{'Agent' if x['role'] == 'agent' else 'You'}: {x['text']}" for x in transcript[-14:])
        for attempt in range(4):
            try:
                time.sleep(self.pause)
                line = self.llm.chat_text(system, f"The call so far:\n{body}\n\nYour next words:")
                line = line.strip().strip('"').split("\n")[0]
                for prefix in ("You:", "Caller:", "Me:"):
                    if line.startswith(prefix):
                        line = line[len(prefix):].strip()
                if line:
                    return line[:300]
            except Exception as e:                                   # rate limit, network: back off and retry
                wait = 2 ** attempt * 3
                print(f"      (caller LLM failed: {str(e)[:80]}; retrying in {wait} s)")
                time.sleep(wait)
        raise RuntimeError("the simulated caller's LLM kept failing")


# ------------------------------------------------------------------------------- audio for voice mode

def wav_samples(audio: bytes) -> tuple[list[int], int]:
    """16-bit mono samples and the rate. Reads the data from its chunk, because Timbre's streamed
    WAV header carries a placeholder length."""
    with wave.open(io.BytesIO(audio)) as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
    data = audio[audio.find(b"data") + 8:]
    if width != 2:
        raise ValueError("expected 16-bit audio")
    n = len(data) // 2
    samples = list(struct.unpack(f"<{n}h", data[: n * 2]))
    if channels == 2:
        samples = samples[::2]
    return samples, rate


def to_wav(samples: list[int], rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(samples)}h", *(max(-32768, min(32767, int(s))) for s in samples)))
    return buf.getvalue()


def phone_quality(samples: list[int], rate: int) -> tuple[list[int], int]:
    """Down to 8 kHz like a phone call: a crude low-pass (averaging) and decimation."""
    step = max(1, round(rate / 8000))
    out = [sum(samples[i:i + step]) / step for i in range(0, len(samples) - step + 1, step)]
    return out, rate // step


def add_noise(samples: list[int], rate: int, snr_db: float, seed: int) -> list[int]:
    """Rain-like noise (filtered noise plus random drops) and a murmur of reversed speech (a crowd),
    at the given signal-to-noise ratio against the speech."""
    rng = random.Random(seed)
    speech_rms = math.sqrt(sum(s * s for s in samples) / max(1, len(samples))) or 1.0
    rain, lp = [], 0.0
    for _ in samples:
        lp = 0.85 * lp + 0.15 * rng.gauss(0, 1)
        drop = rng.gauss(0, 6) if rng.random() < 0.002 else 0.0
        rain.append(lp + drop)
    babble = samples[::-1]
    shift = len(samples) // 3
    babble = babble[shift:] + babble[:shift]
    noise = [r * 0.7 + b / speech_rms * 0.6 for r, b in zip(rain, babble)]
    noise_rms = math.sqrt(sum(x * x for x in noise) / max(1, len(noise))) or 1.0
    scale = speech_rms / (10 ** (snr_db / 20)) / noise_rms
    return [s + x * scale for s, x in zip(samples, noise)]


def degrade(audio: bytes, phone: bool, snr_db: Optional[float], seed: int) -> bytes:
    if not phone and snr_db is None:
        return audio
    samples, rate = wav_samples(audio)
    if snr_db is not None:
        samples = add_noise(samples, rate, snr_db, seed)
    if phone:
        samples, rate = phone_quality(samples, rate)
    return to_wav(samples, rate)


class NoAgentVoice:
    """The agent's replies aren't spoken in a test: no credits, and nobody listens."""
    api_calls = 0

    async def synthesize(self, text, lang):
        return b""

    def cached_path(self, text, lang):
        return Path("not-spoken.wav")


# ------------------------------------------------------------------------------- one call

class MemoryStore:
    def save(self, t):
        pass


def run_call(scenario: dict, caller: LLMCaller, llm, condition: dict, voice: Optional[dict], seed: int) -> dict:
    session = CallSession(Ticket(id=f"{random.randint(1000, 9999)}", caller_number="SIM-STRESS"), llm, MemoryStore())
    greeting = session.greeting()
    transcript = [{"role": "agent", "text": greeting, "lang": "hi-IN"}]
    turns, after_wait = [], 0
    state = None
    if voice:
        from app.voice.call import VoiceState
        state = VoiceState()
    for turn in range(1, MAX_CALLER_TURNS + 1):
        code = lang_at(scenario, turn)
        line = caller.say(scenario, turn, transcript)
        record = {"turn": turn, "caller_lang": code, "said": line}
        started = time.perf_counter()
        if voice:
            res = asyncio.run(_voice_turn(session, state, line, code, condition, voice, seed + turn))
            record["heard"] = res.get("heard")
        else:
            res = session.handle(line, stt_tag(code))
            record["heard"] = line
        record.update({
            "ms": round((time.perf_counter() - started) * 1000),
            "reply": res.get("reply") or "", "reply_lang": res.get("reply_lang"), "action": res.get("action"),
            "waiting": bool(res.get("waiting")), "done": bool(res.get("done")),
            "lang_check": res.get("lang_check"), "understood": res.get("understood"),
            "used_llm": res.get("used_llm"), "stt_ms": res.get("stt_ms"),
        })
        turns.append(record)
        transcript.append({"role": "caller", "text": record["heard"] or "(not heard)", "lang": code})
        if record["reply"]:
            transcript.append({"role": "agent", "text": record["reply"], "lang": record["reply_lang"]})
        if record["done"]:
            break
        if record["waiting"]:
            after_wait += 1
            if after_wait > TURNS_AFTER_WAITING:
                break
    return {"greeting": greeting, "turns": turns, "ticket": session.ticket.model_dump(),
            "waiting": session.waiting, "done": session.done}


async def _voice_turn(session, state, line, code, condition, voice, seed):
    from app.voice.call import voice_turn
    audio = await voice["caller_tts"].synthesize(line, stt_tag(code))
    audio = degrade(audio, condition["phone"], condition["snr"], seed)
    return await voice_turn(session, state, audio, "turn.wav", voice["stt"], NoAgentVoice())


# ------------------------------------------------------------------------------- scoring

CHILD = {"child", "infant"}
ORDINAL = {"ground": 0, "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}


def score(scenario: dict, call: dict, text_mode: bool = True) -> dict:
    truth, t = scenario["truth"], call["ticket"]
    loc, danger = t["location"], t["danger"]
    checks: dict[str, bool] = {}
    if "locality" in truth:
        checks["area"] = truth["locality"] in (loc.get("locality") or "").lower()
    if "pincode" in truth:
        checks["PIN code"] = loc.get("pincode") == truth["pincode"]
    if "people_count" in truth:
        checks["people"] = t.get("people_count") == truth["people_count"]
    if "vulnerable" in truth:
        have = set(t.get("vulnerable") or [])
        checks["vulnerable"] = all((v in have) or (v in CHILD and have & CHILD) for v in truth["vulnerable"])
    if "floor" in truth:
        floor = str(loc.get("floor") or "").lower()
        checks["floor"] = truth["floor"] in floor or str(ORDINAL.get(truth["floor"], "?")) in floor
    if "water_level" in truth:
        checks["water"] = danger.get("water_level") == truth["water_level"]
    if "injured" in truth:
        checks["injured"] = bool(danger.get("injured")) == truth["injured"]
    if "priority" in truth:
        checks["priority"] = t.get("priority") == truth["priority"]
    if "end" in truth:
        end = "waiting" if call["waiting"] else ("done" if call["done"] else "still asking")
        checks["call end"] = end == truth["end"] or (truth["end"] == "handoff" and end == "waiting")

    faults: list[str] = []
    turns = call["turns"]
    previous_reply, asked = None, {}
    for i, x in enumerate(turns):
        reply, n = x["reply"], x["turn"]
        if reply and sounds_like_promise(reply):
            faults.append(f"turn {n}: sounds like a promise or a time: {reply[:80]}")
        if reply and previous_reply and reply == previous_reply:
            faults.append(f"turn {n}: said the exact same thing again")
        if reply and x["reply_lang"] and detect_script_language(reply) not in (x["reply_lang"], "en-IN") \
                and x["reply_lang"] != "en-IN":
            faults.append(f"turn {n}: reply not in its own script ({x['reply_lang']})")
        # language: once the caller has spoken a new language for 2 turns, the reply must follow
        want = stt_tag(x["caller_lang"])
        if i >= 1 and stt_tag(turns[i - 1]["caller_lang"]) == want and x["reply_lang"] != want and reply:
            faults.append(f"turn {n}: caller speaks {LANG_NAMES.get(want, want)}, reply in "
                          f"{LANG_NAMES.get(x['reply_lang'], x['reply_lang'])}")
        action = x["action"] or ""
        if action.startswith("ask:"):
            asked[action] = asked.get(action, 0) + 1
            if asked[action] == 4:            # area may legitimately take 3 (area, simpler, "what can you see")
                faults.append(f"turn {n}: asked {action[4:]} a fourth time")
        if text_mode and reply and x["reply_lang"] and phrases.has("one_person", x["reply_lang"]) \
                and phrases.say("one_person", x["reply_lang"]) in reply:
            faults.append(f"turn {n}: 'give the phone to one person' with perfect audio")
        if (x.get("understood") or {}).get("llm_failed"):
            faults.append(f"turn {n}: the LLM call failed (facts on this turn were lost)")
        if not text_mode and not (x["heard"] or "").strip():
            faults.append(f"turn {n}: Prisma heard nothing")
        previous_reply = reply or previous_reply
    if call["turns"] and not call["waiting"] and not call["done"]:
        faults.append(f"call didn't finish in {MAX_CALLER_TURNS} caller turns")
    right = sum(checks.values())
    return {"checks": checks, "right": right, "total": len(checks), "faults": faults}


# ------------------------------------------------------------------------------- report

def transcript_text(scenario: dict, condition: dict, call: dict, result: dict) -> str:
    out = [f"# {scenario['title']}  [{condition['name']}]", "", f"Facts: {scenario['facts']}",
           f"Behaviour: {scenario['behaviour']}", "", f"AGENT: {call['greeting']}"]
    for x in call["turns"]:
        heard = "" if x["heard"] == x["said"] else f"\n        (Prisma heard: {x['heard'] or '(nothing)'})"
        lc = x.get("lang_check") or {}
        out.append(f"CALLER [{x['caller_lang']}]: {x['said']}{heard}")
        out.append(f"AGENT [{x['action']}, {x['reply_lang']}, {x['ms']} ms"
                   f"{', LLM said ' + str(lc.get('llm')) if lc.get('llm') else ''}]: {x['reply'] or '(silence)'}")
    t = call["ticket"]
    loc = t["location"]
    out += ["", "TICKET: " + json.dumps({
        "priority": t["priority"], "area": loc.get("locality"), "pincode": loc.get("pincode"),
        "street": loc.get("street"), "door": loc.get("door_no"), "building": loc.get("building"),
        "floor": loc.get("floor"), "landmark": loc.get("landmark"), "people": t.get("people_count"),
        "vulnerable": t.get("vulnerable"), "water": t["danger"].get("water_level"),
        "injured": t["danger"].get("injured"), "follow-up": t.get("followup_reasons")}, ensure_ascii=False)]
    out += ["", "CHECKS: " + ", ".join(f"{k} {'ok' if v else 'WRONG'}" for k, v in result["checks"].items())]
    out += ["FAULTS:"] + [f"  - {f}" for f in result["faults"]] + ([] if result["faults"] else ["  (none)"])
    return "\n".join(out) + "\n"


def write_report(out_dir: Path, rows: list[dict], args) -> Path:
    lines = [f"# Surgeline stress test, {datetime.now():%d %b %Y %H:%M}", "",
             f"Mode: **{args.mode}**" + (" (synthetic voices: results flatter real callers)" if args.mode == "voice" else ""),
             f"Model: {settings.llm_model}", ""]
    total_right = sum(r["result"]["right"] for r in rows)
    total = sum(r["result"]["total"] for r in rows)
    faults = sum(len(r["result"]["faults"]) for r in rows)
    lines += [f"**{total_right} of {total} ticket checks right ({100 * total_right / max(1, total):.0f}%), "
              f"{faults} faults in {len(rows)} calls.**", "",
              "| Scenario | Condition | Checks right | Wrong | Faults | Turns |", "|---|---|---|---|---|---|"]
    for r in rows:
        res = r["result"]
        wrong = ", ".join(k for k, v in res["checks"].items() if not v) or "-"
        lines.append(f"| {r['scenario']} | {r['condition']} | {res['right']}/{res['total']} | {wrong} | "
                     f"{len(res['faults'])} | {len(r['call']['turns'])} |")
    lines += ["", "## Faults by call", ""]
    for r in rows:
        if r["result"]["faults"]:
            lines.append(f"**{r['scenario']} [{r['condition']}]** (transcript: calls/{r['file']})")
            lines += [f"- {f}" for f in r["result"]["faults"]]
            lines.append("")
    path = out_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------------------------- main

def conditions(args) -> list[dict]:
    if args.mode == "text":
        return [{"name": "text", "phone": False, "snr": None}]
    out = []
    for level in args.noise.split(","):
        level = level.strip()
        snr = None if level == "clean" else float(level)
        name = ("phone, " if args.phone else "") + ("clean" if snr is None else f"noise {level} dB")
        out.append({"name": name, "phone": args.phone, "snr": snr})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["text", "voice"], default="text")
    ap.add_argument("--only", default="", help="comma-separated scenario ids")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--noise", default="clean", help="voice mode: clean and/or SNR in dB, e.g. clean,10,5")
    ap.add_argument("--phone", action="store_true", help="voice mode: 8 kHz phone-quality audio")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between caller LLM calls (rate limits)")
    args = ap.parse_args()

    from app.llm import make_llm
    llm = make_llm()
    if settings.llm_provider != "openai_compat":
        print("Set LLM_PROVIDER=openai_compat in .env: the simulated caller needs a real LLM.")
        return 1
    voice = None
    if args.mode == "voice":
        if not settings.gnani_api_key:
            print("GNANI_API_KEY is not set in .env")
            return 1
        import httpx
        from app.voice.call import keyterms
        from app.voice.stt import PrismaSTT
        from app.voice.tts import TimbreTTS
        client = httpx.AsyncClient(timeout=settings.gnani_timeout)
        voice = {"stt": PrismaSTT(client, keyterms=keyterms()),
                 "caller_tts": TimbreTTS(client, voices=settings.sim_caller_voices)}

    wanted = {s.strip() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if not wanted or s["id"] in wanted]
    if wanted - {s["id"] for s in scenarios}:
        print("Unknown scenario ids:", ", ".join(sorted(wanted - {s["id"] for s in scenarios})))
        return 1
    out_dir = Path("stress_results") / datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / "calls").mkdir(parents=True, exist_ok=True)
    caller = LLMCaller(llm, args.pause)
    rows = []
    jobs = [(s, c, r) for s in scenarios for c in conditions(args) for r in range(args.repeat)]
    for i, (scenario, condition, rep) in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {scenario['id']}  [{condition['name']}]" + (f"  run {rep + 1}" if args.repeat > 1 else ""))
        try:
            call = run_call(scenario, caller, llm, condition, voice, seed=1000 * i)
        except Exception as e:
            print(f"      FAILED: {e}")
            continue
        result = score(scenario, call, text_mode=args.mode == "text")
        name = f"{scenario['id']}-{condition['name'].replace(', ', '-').replace(' ', '')}-{rep + 1}.txt"
        (out_dir / "calls" / name).write_text(transcript_text(scenario, condition, call, result), encoding="utf-8")
        rows.append({"scenario": scenario["id"], "condition": condition["name"], "run": rep + 1,
                     "file": name, "call": call, "result": result})
        print(f"      {result['right']}/{result['total']} checks right, {len(result['faults'])} faults")
    (out_dir / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    report = write_report(out_dir, rows, args)
    print(f"\nReport: {report.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())