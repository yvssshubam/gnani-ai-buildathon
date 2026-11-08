"""Play a whole voice call from recordings: one audio file per caller turn, in order.

Start the server first (terminal 1):  uvicorn app.main:app --reload --port 8000
Then (terminal 2), from flood-sos/backend with the venv active:
    python scripts\\voice_cli.py rec\\call1_*.m4a
    python scripts\\voice_cli.py t1.wav t2.wav t3.wav --play     # also play the agent's replies (Windows)

Record each answer as a separate clip on your phone (WAV, MP3, M4A, OGG, FLAC or AAC, at most 30 s).
The agent's spoken replies are saved to scripts/out/call_<id>/.
"""
import argparse
import glob
import json
import sys
import time
from pathlib import Path

import httpx

OUT_DIR = Path(__file__).resolve().parent / "out"


def play(path: Path) -> None:
    try:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
    except ImportError:
        pass  # not Windows: open the saved files instead


def save_audio(client: httpx.Client, server: str, urls: list, folder: Path, prefix: str, do_play: bool) -> None:
    for i, url in enumerate(urls, 1):
        if not url:
            print("    (no audio for this part)")
            continue
        path = folder / f"{prefix}_part{i}.wav"
        path.write_bytes(client.get(server + url).content)
        if do_play:
            play(path)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+", help="caller turns in order (wildcards allowed)")
    p.add_argument("--server", default="http://localhost:8000")
    p.add_argument("--play", action="store_true", help="play the agent's replies (Windows)")
    args = p.parse_args()

    files: list[Path] = []
    for pattern in args.files:  # Windows cmd doesn't expand *.wav itself
        matches = sorted(glob.glob(pattern)) or [pattern]
        files.extend(Path(m) for m in matches)
    for f in files:
        if not f.exists():
            sys.exit(f"File not found: {f}")

    with httpx.Client(timeout=60) as client:
        r = client.post(f"{args.server}/api/voice/calls", json={})
        if r.status_code != 200:
            sys.exit(f"Could not start a call: HTTP {r.status_code} {r.text}")
        call = r.json()
        call_id = call["call_id"]
        folder = OUT_DIR / f"call_{call_id}"
        folder.mkdir(parents=True, exist_ok=True)
        print(f"Call {call_id}  (replies saved to {folder})\n")
        print(f"AGENT [{call['greeting_lang']}]: {call['greeting']}   (tts {call['tts_ms']} ms)")
        save_audio(client, args.server, call["audio"], folder, "00_greeting", args.play)

        for n, f in enumerate(files, 1):
            started = time.perf_counter()
            r = client.post(f"{args.server}/api/voice/calls/{call_id}/turn",
                            params={"filename": f.name}, content=f.read_bytes())
            total = round((time.perf_counter() - started) * 1000)
            if r.status_code != 200:
                print(f"\nTURN {n} ({f.name}): HTTP {r.status_code} {r.text}")
                continue
            res = r.json()
            llm = "LLM" if res.get("used_llm") else "quick" if res.get("action") != "not_heard" else "-"
            print(f"\nCALLER [{res['heard_lang']}] ({f.name}): {res['heard']!r}")
            print(f"AGENT  [{res['reply_lang']}] {res['action']} / {llm}: {res['reply']}")
            print(f"    stt {res['stt_ms']} ms | engine {res.get('turn_ms', 0)} ms | "
                  f"tts {res['tts_ms']} ms | total {total} ms")
            if res.get("tts_error"):
                print(f"    TTS error: {res['tts_error']}")
            save_audio(client, args.server, res["audio"], folder, f"{n:02d}_agent", args.play)
            if res.get("done"):
                break

        ticket = client.get(f"{args.server}/api/tickets/{call_id}").json()
        ticket.pop("transcript", None)
        print("\nTICKET:")
        print(json.dumps(ticket, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()