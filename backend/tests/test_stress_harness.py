"""The stress-test harness itself, offline: scripted caller, fake LLM, synthetic audio."""
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import stress_test as st  # noqa: E402
from stress_scenarios import SCENARIOS  # noqa: E402

from app.llm import FakeLLM  # noqa: E402


class ScriptedCaller:
    def __init__(self, lines):
        self.lines = list(lines)

    def say(self, scenario, turn, transcript):
        return self.lines.pop(0) if self.lines else "yes"


SCENARIO = {
    "id": "t", "title": "test", "facts": "", "behaviour": "", "langs": [(1, "en-IN")],
    "truth": {"locality": "velachery", "people_count": 4, "water_level": "knee", "priority": "P0", "end": "waiting"},
}


def test_a_call_runs_and_is_scored():
    caller = ScriptedCaller(["Water in our house in Velachery, my grandmother is with us, water rising",
                             "nobody is hurt", "Bharathi street, door no 12, first floor",
                             "we are 4 people", "water is at knee level", "yes correct", "ok", "ok"])
    call = st.run_call(SCENARIO, caller, FakeLLM(), {"name": "text", "phone": False, "snr": None}, None, seed=1)
    result = st.score(SCENARIO, call)
    assert result["checks"] == {"area": True, "people": True, "water": True, "priority": True, "call end": True}
    assert call["waiting"] and len(call["turns"]) <= st.MAX_CALLER_TURNS
    text = st.transcript_text(SCENARIO, {"name": "text"}, call, result)
    assert "CALLER [en-IN]: nobody is hurt" in text and "CHECKS:" in text


def test_faults_are_found():
    call = {"greeting": "g", "waiting": False, "done": False, "ticket": {
        "location": {"locality": None}, "danger": {}, "priority": "P1", "people_count": None, "vulnerable": []},
        "turns": [
            {"turn": 1, "caller_lang": "te-IN", "said": "a", "heard": "a", "reply": "Okay. Where are you?",
             "reply_lang": "en-IN", "action": "ask:area", "understood": {"llm_failed": True}},
            {"turn": 2, "caller_lang": "te-IN", "said": "b", "heard": "b", "reply": "Okay. Where are you?",
             "reply_lang": "en-IN", "action": "ask:area", "understood": {}},
        ]}
    faults = " | ".join(st.score(SCENARIO, call)["faults"])
    assert "LLM call failed" in faults and "exact same thing again" in faults
    assert "caller speaks Telugu, reply in English" in faults and "didn't finish" in faults


def test_report_is_written(tmp_path):
    rows = [{"scenario": "t", "condition": "text", "run": 1, "file": "t.txt",
             "call": {"turns": []}, "result": {"checks": {"area": False}, "right": 0, "total": 1, "faults": ["x"]}}]
    path = st.write_report(tmp_path, rows, SimpleNamespace(mode="text"))
    body = path.read_text(encoding="utf-8")
    assert "0 of 1 ticket checks right" in body and "| t | text | 0/1 | area | 1 |" in body


def streamed_wav(seconds=1.0, rate=16000):
    n = int(rate * seconds)
    pcm = struct.pack(f"<{n}h", *(int(8000 * ((i // 20) % 2 * 2 - 1)) for i in range(n)))
    return (b"RIFF" + struct.pack("<I", 0xFFFFFFFF) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", 0xFFFFFFFF) + pcm)


def test_audio_is_made_phone_quality_and_noisy():
    out = st.degrade(streamed_wav(), phone=True, snr_db=5, seed=1)
    samples, rate = st.wav_samples(out)
    assert rate == 8000 and abs(len(samples) - 8000) <= 2
    clean, _ = st.phone_quality(st.wav_samples(streamed_wav())[0], 16000)
    assert samples != [round(x) for x in clean]              # noise was added
    assert st.degrade(streamed_wav(), phone=False, snr_db=None, seed=1) == streamed_wav()


def test_every_scenario_is_well_formed():
    ids = [s["id"] for s in SCENARIOS]
    assert len(ids) == len(set(ids)) == 12
    for s in SCENARIOS:
        assert s["facts"] and s["behaviour"] and s["truth"]
        assert all(code in st.LANG_DESC for _, code in s["langs"])
        assert s["truth"].get("end") in ("waiting", "done", "handoff")