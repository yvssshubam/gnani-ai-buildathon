"""Run your own test calls from files: drop a .txt file per call into a folder, run this, read the report.

    python scripts\\replay_calls.py                        # every .txt in test_calls\\
    python scripts\\replay_calls.py test_calls\\my_call.txt  # one file
    python scripts\\replay_calls.py my_folder\\             # another folder

Nothing in the app changes: each call goes through the same engine as a live call, and the results go
to stress_results\\<date-time>\\ (report.md, a transcript per call), like scripts\\stress_test.py.

A call file is one of three kinds (see test_calls\\HOW_TO_WRITE_A_CALL.txt):

1. A pasted transcript, exactly as copied from the call screen: lines alternate agent / caller,
   starting with the agent's greeting. Agent lines are skipped; your caller lines are replayed word
   for word, in order.
2. Marked lines: "CALLER: ..." / "CALLER [te]: ..." (AGENT lines are skipped). A caller line
   "@path\\to\\clip.wav" sends that recording through Prisma (needs GNANI_API_KEY).
3. A fact sheet: "# facts: ..." and "# behaviour: ..." (and optionally "# langs: 1=hi, 3=te") with no
   caller lines. An LLM plays the caller, as in the stress test (uses Groq).

Optional header lines, anywhere in the file:
    # title: what this call tests
    # expect: priority=P0; end=waiting; area=velachery; pincode=600042; people=4;
    #         vulnerable=elderly|child; water=knee; injured=no; floor=second
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import stress_test as st  # noqa: E402

from app.config import settings  # noqa: E402
from app.dialogue import CallSession  # noqa: E402
from app.language import detect_script_language  # noqa: E402
from app.models import Ticket  # noqa: E402

SHORT = {"hi": "hi-IN", "en": "en-IN", "te": "te-IN", "ta": "ta-IN", "hinglish": "hi-IN-latn"}
EXPECT_KEYS = {"priority": "priority", "end": "end", "area": "locality", "pincode": "pincode",
               "people": "people_count", "vulnerable": "vulnerable", "water": "water_level",
               "injured": "injured", "floor": "floor"}


# ------------------------------------------------------------------------------- reading a call file

def lang_code(tag: str, text: str) -> str:
    """"te" / "te-IN" / "hinglish" -> our code; no tag -> from the script of the line."""
    tag = (tag or "").strip().lower()
    if tag in SHORT:
        return SHORT[tag]
    if tag.endswith("-in") and tag[:2] in SHORT:
        return SHORT[tag[:2]]
    return detect_script_language(text) or "en-IN"


def parse_expect(text: str) -> dict:
    truth = {}
    for part in text.replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        key, value = (x.strip() for x in part.split("=", 1))
        key = EXPECT_KEYS.get(key.lower())
        if not key or not value:
            continue
        if key == "people_count":
            truth[key] = int(value)
        elif key == "vulnerable":
            truth[key] = [v.strip().lower() for v in value.replace(",", "|").split("|") if v.strip()]
        elif key == "injured":
            truth[key] = value.lower() in ("yes", "true", "1", "haan")
        elif key in ("priority",):
            truth[key] = value.upper()
        else:
            truth[key] = value.lower()
    return truth


def parse_call_file(path: Path) -> dict:
    """{id, title, truth, lines: [(lang_code, text_or_@audio)], facts, behaviour, langs}"""
    raw = path.read_text(encoding="utf-8-sig").splitlines()
    call = {"id": path.stem, "title": path.stem, "truth": {}, "lines": [], "facts": "", "behaviour": "",
            "langs": [(1, "hi-IN")], "path": path}
    body, expect_parts = [], []
    for line in raw:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            head = s.lstrip("#").strip()
            key, _, value = head.partition(":")
            key = key.strip().lower()
            if key == "title":
                call["title"] = value.strip()
            elif key == "expect":
                expect_parts.append(value)
            elif key == "facts":
                call["facts"] = value.strip()
            elif key in ("behaviour", "behavior"):
                call["behaviour"] = value.strip()
            elif key == "langs":
                langs = []
                for part in value.split(","):
                    turn, _, tag = part.partition("=")
                    if turn.strip().isdigit():
                        langs.append((int(turn), lang_code(tag, "")))
                call["langs"] = langs or call["langs"]
            elif expect_parts and "=" in head and ":" not in head:
                expect_parts.append(head)          # an expect list continued on the next line
            continue
        body.append(s)
    call["truth"] = parse_expect(";".join(expect_parts))

    marked = any(_speaker(b)[0] for b in body)
    if marked:
        for b in body:
            who, tag, text = _speaker(b)
            if who == "caller":
                call["lines"].append((lang_code(tag, text), text))
    else:
        # a pasted transcript: agent (greeting), caller, agent, caller, ...
        for i, b in enumerate(body):
            if i % 2 == 1:
                call["lines"].append((lang_code("", b), b))
    return call


def _speaker(line: str) -> tuple:
    """("caller"|"agent"|None, lang tag, text) for "CALLER [te]: text" / "AGENT: text"."""
    head, sep, text = line.partition(":")
    if not sep:
        return None, "", line
    word = head.strip()
    tag = ""
    if "[" in word and word.endswith("]"):
        word, tag = word[:-1].split("[", 1)
    word = word.strip().lower()
    if word in ("caller", "c", "me", "user"):
        return "caller", tag, text.strip()
    if word in ("agent", "a", "surgeline", "ai"):
        return "agent", tag, text.strip()
    return None, "", line


# ------------------------------------------------------------------------------- playing a call

def replay(call: dict, llm, voice) -> dict:
    """Feed the caller lines in order, exactly as written (or recorded)."""
    session = CallSession(Ticket(id=str(abs(hash(call["id"])) % 9000 + 1000), caller_number="SIM-REPLAY"),
                          llm, st.MemoryStore())
    greeting = session.greeting()
    state = None
    if any(text.startswith("@") for _, text in call["lines"]):
        from app.voice.call import VoiceState
        state = VoiceState()
    turns = []
    for n, (code, text) in enumerate(call["lines"], 1):
        record = {"turn": n, "caller_lang": code, "said": text}
        if text.startswith("@"):
            res = asyncio.run(_audio_turn(session, state, call["path"].parent / text[1:].strip(), voice))
            record["heard"] = res.get("heard")
        else:
            res = session.handle(text, st.stt_tag(code))
            record["heard"] = text
        record.update({"ms": res.get("turn_ms") or 0, "reply": res.get("reply") or "",
                       "reply_lang": res.get("reply_lang"), "action": res.get("action"),
                       "waiting": bool(res.get("waiting")), "done": bool(res.get("done")),
                       "lang_check": res.get("lang_check"), "understood": res.get("understood")})
        turns.append(record)
        if record["done"]:
            if n < len(call["lines"]):
                record["note"] = f"call ended; {len(call['lines']) - n} caller line(s) not used"
            break
    return {"greeting": greeting, "turns": turns, "ticket": session.ticket.model_dump(),
            "waiting": session.waiting, "done": session.done}


async def _audio_turn(session, state, wav: Path, voice):
    from app.voice.call import voice_turn
    if voice is None:
        raise RuntimeError("this call has recordings (@file.wav): set GNANI_API_KEY in .env")
    if not wav.exists():
        raise FileNotFoundError(f"recording not found: {wav}")
    return await voice_turn(session, state, wav.read_bytes(), wav.name, voice["stt"], st.NoAgentVoice())


# ------------------------------------------------------------------------------- main

def collect(paths: list[str]) -> list[Path]:
    targets = [Path(p) for p in paths] or [Path("test_calls")]
    files = []
    for t in targets:
        if t.is_dir():
            files += sorted(p for p in t.glob("*.txt") if not p.name.upper().startswith("HOW_TO"))
        elif t.exists():
            files.append(t)
        else:
            print(f"Not found: {t}")
    return files


def main() -> int:
    files = collect(sys.argv[1:])
    if not files:
        print("No call files found. Put .txt files in backend\\test_calls\\ (see HOW_TO_WRITE_A_CALL.txt).")
        return 1
    from app.llm import make_llm
    llm = make_llm()
    if settings.llm_provider != "openai_compat":
        print("WARNING: LLM_PROVIDER is not openai_compat, so the offline stand-in reads the calls: it only\n"
              "understands English keywords. Set LLM_PROVIDER=openai_compat in .env to test for real.\n")
    calls = [parse_call_file(f) for f in files]
    voice = None
    if any(text.startswith("@") for c in calls for _, text in c["lines"]) and settings.gnani_api_key:
        import httpx
        from app.voice.call import keyterms
        from app.voice.stt import PrismaSTT
        voice = {"stt": PrismaSTT(httpx.AsyncClient(timeout=settings.gnani_timeout), keyterms=keyterms())}
    if any(not c["lines"] for c in calls) and settings.llm_provider != "openai_compat":
        print("A fact-sheet call needs a real LLM: set LLM_PROVIDER=openai_compat in .env.")
        return 1

    out_dir = Path("stress_results") / datetime.now().strftime("%Y%m%d-%H%M%S")
    (out_dir / "calls").mkdir(parents=True, exist_ok=True)
    rows = []
    for i, c in enumerate(calls, 1):
        kind = "replay" if c["lines"] else "LLM caller"
        print(f"[{i}/{len(calls)}] {c['id']}  ({kind}, {len(c['lines']) or 'free'} caller lines)")
        scenario = {"id": c["id"], "title": c["title"], "facts": c["facts"] or "(replayed lines)",
                    "behaviour": c["behaviour"] or "(as written in the file)", "langs": c["langs"], "truth": c["truth"]}
        try:
            if c["lines"]:
                result_call = replay(c, llm, voice)
            else:
                caller = st.LLMCaller(llm, 12.0, "openai/gpt-oss-120b")
                result_call = st.run_call(scenario, caller, llm, {"name": "text", "phone": False, "snr": None}, None, 1)
        except Exception as e:
            print(f"      FAILED: {e}")
            continue
        result = st.score(scenario, result_call, text_mode=not any(t.startswith("@") for _, t in c["lines"]))
        if c["lines"] and not result_call["waiting"] and not result_call["done"]:
            # a replay ends when its lines run out: that isn't a fault of the agent
            result["faults"] = [f for f in result["faults"] if "didn't finish" not in f]
        name = f"{c['id']}.txt"
        (out_dir / "calls" / name).write_text(
            st.transcript_text(scenario, {"name": kind}, result_call, result), encoding="utf-8")
        rows.append({"scenario": c["id"], "condition": kind, "run": 1, "file": name,
                     "call": result_call, "result": result})
        checks = f"{result['right']}/{result['total']} checks right, " if result["total"] else ""
        print(f"      {checks}{len(result['faults'])} faults")
    report = st.write_report(out_dir, rows, SimpleNamespace(mode="replay from files"))
    print(f"\nReport: {report.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())