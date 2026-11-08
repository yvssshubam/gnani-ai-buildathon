"""Phase 2, step 1: check the Gnani key, model access and real latency before building voice.

What it does (a few credits in total):
  1. Timbre v2.5 TTS: speaks one Hindi agent line that contains a ticket number.
  2. Prisma v3.0 STT: sends that audio back with the same settings the call will use
     (4 language hints, codemix, area-name keyterms, previous question as context).
  3. Prints the transcript, detected language and latency of each call.

Run from flood-sos/backend with the venv active:
    python scripts\\gnani_check.py                    # TTS -> STT round trip
    python scripts\\gnani_check.py --wav my_call.wav  # also transcribe your own recording
    python scripts\\gnani_check.py --voice Chitra     # try another Hindi voice

Audio is saved to scripts/out/ so you can listen to it.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "https://api.vachana.ai"
STT_URL = f"{BASE_URL}/stt/v3"
TTS_URL = f"{BASE_URL}/api/v1/tts/inference"

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = Path(__file__).resolve().parent / "out"

# Same settings the live call will use.
STT_MODEL = "prisma-v3.0"
STT_LANGUAGES = "ta-IN,hi-IN,en-IN,te-IN"  # hints, not a lock (max 4)
STT_FORMAT = "codemix"
KEYTERMS = ["Velachery", "வேளச்சேரி", "Tambaram", "Adyar", "Madipakkam",
            "Gandhi Street", "first floor", "second floor"]
TTS_MODEL = "timbre-v2.5"

# The ticket number twice: once as digits, once as words. Listen to which one Timbre reads right.
TEST_LINE = ("आपकी शिकायत दर्ज हो गई है। आपका टिकट नंबर 5 2 3 4 है, "
             "यानी पाँच दो तीन चार। बचाव दल को सूचना दे दी गई है।")
PREVIOUS_QUESTION = "आपका टिकट नंबर नोट कर लीजिए।"


def load_api_key() -> str:
    """GNANI_API_KEY from the environment, else from backend/.env."""
    key = os.environ.get("GNANI_API_KEY", "").strip()
    env_file = BACKEND_DIR / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GNANI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit(f"GNANI_API_KEY is not set. Add GNANI_API_KEY=... to {env_file}")
    return key


def explain_error(r: httpx.Response) -> str:
    hints = {
        401: "key missing or invalid. Check that it's the Speech API key (X-API-Key-ID), not an Agent Builder key.",
        402: "out of credits on this account.",
        403: "this key isn't allowed to use this API or model. Ask Gnani to enable Prisma v3.0 / Timbre v2.5.",
        422: "a required field is missing.",
    }
    try:
        body = json.dumps(r.json(), ensure_ascii=False)
    except ValueError:
        body = r.text[:300]
    return f"HTTP {r.status_code}: {hints.get(r.status_code, '')}\n    {body}"


def post_with_retry(client: httpx.Client, url: str, **kwargs) -> tuple[httpx.Response, float]:
    """POST with backoff on 429 (some accounts allow only one active request). Returns (response, seconds)."""
    delay = 1.0
    for attempt in range(5):
        start = time.perf_counter()
        r = client.post(url, **kwargs)
        elapsed = time.perf_counter() - start
        if r.status_code != 429:
            return r, elapsed
        print(f"    429 rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/5)")
        time.sleep(delay)
        delay *= 2
    return r, elapsed


def tts(client: httpx.Client, key: str, text: str, voice: str, lang: str) -> tuple[bytes, float]:
    body = {
        "text": text,
        "voice": voice,
        "model": TTS_MODEL,
        "language": lang,
        "speed": 1.0,
        "audio_config": {
            "sample_rate": 16000,  # enough for speech, and a smaller upload to STT
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    r, secs = post_with_retry(client, TTS_URL, json=body,
                              headers={"X-API-Key-ID": key, "Content-Type": "application/json"})
    if r.status_code != 200:
        raise RuntimeError("TTS failed: " + explain_error(r))
    if not r.headers.get("content-type", "").startswith("audio"):
        raise RuntimeError(f"TTS returned {r.headers.get('content-type')} instead of audio: {r.text[:300]}")
    return r.content, secs


def stt(client: httpx.Client, key: str, wav_path: Path, previous_text: str | None) -> tuple[dict, float]:
    data = {
        "model": STT_MODEL,
        "language_code": STT_LANGUAGES,
        "format": STT_FORMAT,
        "keyterms": json.dumps(KEYTERMS, ensure_ascii=False),
    }
    if previous_text:
        data["previous_text"] = previous_text
    with open(wav_path, "rb") as f:
        r, secs = post_with_retry(client, STT_URL, data=data,
                                  files={"audio_file": (wav_path.name, f, "audio/wav")},
                                  headers={"X-API-Key-ID": key})
    if r.status_code != 200:
        raise RuntimeError("STT failed: " + explain_error(r))
    return r.json(), secs


def print_stt(result: dict, secs: float) -> None:
    print(f"    transcript : {result.get('transcript')!r}")
    print(f"    language   : {result.get('detected_language_code', '(not returned)')}")
    print(f"    latency    : {secs:.2f}s round trip"
          f" (server: {result.get('processing_time', '?')}s processing,"
          f" {result.get('end_to_end_latency', '?')}s end to end)")
    if result.get("truncated"):
        print("    WARNING: transcript was truncated")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    except AttributeError:
        pass

    p = argparse.ArgumentParser(description="Check Gnani Prisma + Timbre access and latency")
    p.add_argument("--voice", default="Yashvi", help="Timbre voice (default: Yashvi)")
    p.add_argument("--lang", default="hi-IN", help="TTS language for the test line (default: hi-IN)")
    p.add_argument("--wav", type=Path, help="also transcribe this recording of your own")
    args = p.parse_args()

    key = load_api_key()
    OUT_DIR.mkdir(exist_ok=True)
    ok = True

    with httpx.Client(timeout=30) as client:
        print(f"1. TTS  ({TTS_MODEL}, voice {args.voice}, {args.lang})")
        tts_wav = OUT_DIR / "tts_test.wav"
        try:
            audio, secs = tts(client, key, TEST_LINE, args.voice, args.lang)
            tts_wav.write_bytes(audio)
            print(f"    OK: {len(audio) / 1024:.0f} KB in {secs:.2f}s, saved to {tts_wav}")
            print("    Listen: is 5 2 3 4 read as digits, and does it match 'पाँच दो तीन चार'?")
        except RuntimeError as e:
            print(f"    {e}")
            ok = False

        if ok:
            print(f"\n2. STT  ({STT_MODEL}, hints {STT_LANGUAGES}, {STT_FORMAT}) on the TTS audio")
            try:
                result, secs = stt(client, key, tts_wav, PREVIOUS_QUESTION)
                print_stt(result, secs)
                if result.get("detected_language_code") != "hi-IN":
                    print("    NOTE: expected hi-IN. Paste this output into the chat.")
            except RuntimeError as e:
                print(f"    {e}")
                ok = False

        if args.wav:
            print(f"\n3. STT on your recording: {args.wav}")
            if not args.wav.exists():
                print("    file not found")
                ok = False
            else:
                try:
                    result, secs = stt(client, key, args.wav, None)
                    print_stt(result, secs)
                except RuntimeError as e:
                    print(f"    {e}")
                    ok = False

    print("\nAll checks passed. Paste this output into the chat." if ok
          else "\nA check failed. Paste this output into the chat.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()