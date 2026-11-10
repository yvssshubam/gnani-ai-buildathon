"""Generate the demo video's voice-over with Gnani Timbre, with the delivery varied line by line.

Run from flood-sos/backend with the venv active (the server doesn't need to be running):
    python scripts\\make_narration.py --play                                  # Timbre v2.5, voice Shlok
    python scripts\\make_narration.py --model timbre-v3.0 --try Shubham,Avinash,Devansh,Prakash,Yashraj --play
    python scripts\\make_narration.py --model timbre-v3.0 --voice Shubham --play
    python scripts\\make_narration.py --only 16 --play                        # redo / hear one line

Modulation, two ways:
  - pace: every line has its own speed (serious lines slower, the call-gap lines a little quicker).
    Works on both models.
  - audio tags such as <pauses> and <slow> inside the text. Only Timbre v3.0 performs them; for v2.5
    this script removes them before sending. v3.0 has its own voices: v2.5 voices like Shlok won't work.

Writes narration\\NN_name.wav and prints each clip's length. Lines already generated with the same
model, voice, pace and text come from narration_cache, so re-running costs nothing.
"""
import argparse
import asyncio
import io
import re
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "app" imports work

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.voice.gnani_http import GnaniError  # noqa: E402
from app.voice.tts import TimbreTTS  # noqa: E402

LANG = "en-IN"
SLOW, CALM, NORMAL, BRISK = 0.88, 0.94, 1.0, 1.06

# (file name, pace, text). Edit here, then re-run: only changed lines cost credits.
LINES = [
    # 1. Intro (0:00-0:40): title card, pain points, dashboard. Serious, unhurried.
    ("01_problem", SLOW, "When a flood hits, the helpline floods too. Every operator is busy. "
                         "Callers wait on hold, hang up, and call again. <pauses> "
                         "<slow> The people in the most danger may never get through."),
    ("02_what", CALM, "<pauses> Surgeline is a voice agent that answers when no operator is free."),
    ("03_how", NORMAL, "It speaks the caller's language, asks only what rescue needs, "
                       "and hands a ready ticket to the control room."),
    ("04_gnani", NORMAL, "It runs on two Gnani models: Prisma, which hears the caller, "
                         "<pauses> and Timbre, the voice they hear."),
    # 2. Dashboard (0:40-1:00). Plain, guided-tour pace.
    ("05_queue", NORMAL, "This is the control room. Calls on the line right now sit at the top, "
                         "then waiting tickets, most urgent first."),
    ("06_map", NORMAL, "The map shows every caller, the areas reported flooded, and where each rescue team is."),
    ("07_incoming", CALM, "Here is a call coming in, <pauses> with every operator busy."),
    # 3. The call, spoken in the gaps between turns. A little quicker, so the call isn't held up.
    ("08_listen", BRISK, "Prisma turns the caller's words into text. Surgeline notes what it already knows, "
                         "and asks only what is missing."),
    ("09_human", BRISK, "The caller asks for a person. The agent is honest: they are in line for an officer, "
                        "and it keeps going."),
    ("10_switch", BRISK, "A neighbour takes the phone and speaks Telugu. Prisma catches the switch, "
                         "and the agent answers in Telugu."),
    ("11_readback", BRISK, "Before it finishes, it reads the address back, "
                           "so a misheard house number is caught on the call."),
    ("12_promise", CALM, "Asked when the boat will come, <pauses> it never promises a time."),
    # 4. The ticket (2:15-2:45). Slows down on the priority.
    ("13_ticket", NORMAL, "The ticket is ready. Each field shows the caller's exact words, and when they were said."),
    ("14_priority", CALM, "Priority comes from fixed rules, not from the AI. Waist-deep, rising water, "
                          "and an eighty-year-old grandmother. <pauses> <slow> P zero."),
    ("15_assign", NORMAL, "Surgeline suggests the nearest boat that can reach deep water. "
                          "One click, <pauses> and the team gets the address by SMS."),
    # 5. End (2:45-3:00). Slow and clear, so the name lands.
    ("16_end", SLOW, "<slow> Surgeline. <pauses> Every call answered, even when every operator is busy. "
                     "<pauses> Built by Y. V. S. S. Shubam, on Gnani Prisma and Timbre."),
]

TAG = re.compile(r"\s*<[a-z ]+>\s*")


def for_model(text: str, model: str) -> str:
    """v3.0 performs the tags; for any other model, take them out (and tidy the spaces)."""
    if model == "timbre-v3.0":
        return " ".join(text.split())
    return " ".join(TAG.sub(" ", text).split())


def clean_wav(wav_bytes: bytes) -> tuple[bytes, float]:
    """Timbre's WAV header says the audio is endless (size 0xFFFFFFFF, as streamed audio does), so
    players and editors show a wrong length. Rewrite the header with the real size; audio unchanged."""
    with wave.open(io.BytesIO(wav_bytes)) as r:
        params = r.getparams()
        frames = r.readframes(r.getnframes())  # stops at the real end of the data
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(frames)
    secs = len(frames) / (params.framerate * params.sampwidth * params.nchannels)
    return out.getvalue(), secs


def play(path: Path) -> None:
    """Play a WAV through the speakers (Windows has this built in). Elsewhere, just say where it is."""
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    else:
        print(f"           (open {path} to listen)")


async def main(model: str, voices: list[str], try_mode: bool, base: float, do_play: bool,
               only: list[str]) -> int:
    if not settings.gnani_api_key:
        print("GNANI_API_KEY is not set in .env")
        return 1
    out = Path("narration")
    out.mkdir(exist_ok=True)
    lines = LINES[:1] if try_mode else LINES
    if only:
        lines = [line for line in lines if any(line[0].startswith(o) for o in only)]
        if not lines:
            print(f"No line starts with {', '.join(only)}. Names: {', '.join(n for n, _, _ in LINES)}")
            return 1
    print(f"Model {model}" + ("" if model == "timbre-v3.0" else " (audio tags removed: only v3.0 performs them)"))
    total, failed = 0.0, 0
    async with httpx.AsyncClient(timeout=settings.gnani_timeout) as client:
        for voice in voices:
            for name, pace, text in lines:
                speed = round(min(1.15, max(0.85, base * pace)), 2)
                tts = TimbreTTS(client, voices={LANG: voice}, fallback_lang=LANG, model=model,
                                speed=speed, cache_dir="narration_cache")
                said = for_model(text, model)
                try:
                    audio = await tts.synthesize(said, LANG)
                except GnaniError as e:
                    failed += 1
                    print(f"  FAILED {voice} {name}: {e}")
                    if e.status in (401, 402, 403):
                        return 1  # wrong key / no credits: every line will fail the same way
                    if e.status in (400, 404, 422) and model == "timbre-v3.0":
                        print("  (v3.0 has its own voices: check the voice name is a v3.0 one, "
                              "and that your key has v3.0)")
                        return 1
                    continue
                dest = out / (f"try_{voice}.wav" if try_mode else f"{name}.wav")
                audio, secs = clean_wav(audio)
                dest.write_bytes(audio)
                total += secs
                print(f"  {voice:8} x{speed:<4} {secs:4.1f}s  {dest}   {said[:55]}")
                if do_play:
                    play(dest)
    if not try_mode:
        print(f"\nTotal voice-over: {total:.1f}s (should be about 2 minutes). Files in {out.resolve()}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", default="timbre-v2.5", choices=["timbre-v2.5", "timbre-v3.0"],
                   help="v3.0 performs the audio tags (default: timbre-v2.5)")
    p.add_argument("--voice", default="", help="narrator voice (male voices by default: Shlok on v2.5, Shubham on v3.0)")
    p.add_argument("--try", dest="try_voices", default="",
                   help="comma-separated voices: render only line 1 in each, to compare")
    p.add_argument("--play", action="store_true", help="play each line out loud after generating it")
    p.add_argument("--only", default="", help="comma-separated line numbers or names, e.g. 16 or 01,09")
    p.add_argument("--speed", type=float, default=1.0,
                   help="scales every line's pace; the result stays within 0.85-1.15 (default 1.0)")
    a = p.parse_args()
    default_voice = "Shubham" if a.model == "timbre-v3.0" else "Shlok"
    voices = [v.strip() for v in a.try_voices.split(",") if v.strip()] or [a.voice or default_voice]
    only = [o.strip().zfill(2) if o.strip().isdigit() else o.strip() for o in a.only.split(",") if o.strip()]
    sys.exit(asyncio.run(main(a.model, voices, bool(a.try_voices), a.speed, a.play, only)))