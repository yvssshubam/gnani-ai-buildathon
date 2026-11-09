"""scripts/replay_calls.py: reading call files and replaying them, offline."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import replay_calls as rc  # noqa: E402
import stress_test as st  # noqa: E402

from app.llm import FakeLLM  # noqa: E402

EXAMPLES = Path(__file__).resolve().parent.parent / "test_calls"


def test_pasted_transcript_keeps_only_the_caller_lines():
    call = rc.parse_call_file(EXAMPLES / "live_1337_off_map_address.txt")
    texts = [t for _, t in call["lines"]]
    assert texts[0] == "किसी की जान को भी खतरा नहीं है।"
    assert "Main Sayanathpuri colony." in texts and texts[-1] == "chest వరకు ఉంది."
    assert not any("बताइए" in t and "इलाके का नाम" in t for t in texts)        # agent lines skipped
    assert len(texts) == 10                                       # the 10 things the caller said
    assert call["lines"][4] == ("en-IN", "Main Sayanathpuri colony.")
    assert call["lines"][0][0] == "hi-IN" and call["lines"][-1][0] == "te-IN"
    assert call["truth"] == {"priority": "P0", "end": "waiting", "locality": "sainath", "people_count": 2,
                             "water_level": "chest", "injured": True}


def test_marked_lines_tags_and_recordings(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("# expect: vulnerable=elderly|child; floor=second\n"
                 "AGENT: hello\nCALLER [te]: నమస్తే\nCALLER [hinglish]: hum second floor pe hain\n"
                 "CALLER: @rec\\one.wav\nCALLER: we are four\n", encoding="utf-8")
    call = rc.parse_call_file(f)
    assert call["lines"] == [("te-IN", "నమస్తే"), ("hi-IN-latn", "hum second floor pe hain"),
                             ("en-IN", "@rec\\one.wav"), ("en-IN", "we are four")]
    assert call["truth"] == {"vulnerable": ["elderly", "child"], "floor": "second"}


def test_fact_sheet_file():
    call = rc.parse_call_file(EXAMPLES / "factsheet_wants_a_person.txt")
    assert call["lines"] == [] and "Tambaram" in call["facts"] and call["langs"] == [(1, "hi-IN")]


def test_a_replay_runs_and_is_scored(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("# expect: area=velachery; people=4; water=knee\n"
                 "CALLER: water in our house in Velachery, my grandmother is with us\n"
                 "CALLER: nobody is hurt\nCALLER: Gandhi street, door no 12, first floor\n"
                 "CALLER: we are 4 people\nCALLER: knee level\nCALLER: yes correct\n", encoding="utf-8")
    call = rc.parse_call_file(f)
    played = rc.replay(call, FakeLLM(), None)
    scenario = {"id": "c", "title": "c", "facts": "", "behaviour": "", "langs": call["langs"], "truth": call["truth"]}
    result = st.score(scenario, played)
    assert result["checks"] == {"area": True, "people": True, "water": True}
    assert [t["said"] for t in played["turns"]][0].startswith("water in our house")


def test_every_example_file_parses():
    for f in rc.collect([str(EXAMPLES)]):
        call = rc.parse_call_file(f)
        assert call["lines"] or call["facts"], f.name