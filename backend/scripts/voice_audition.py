"""Hear the agent's lines in several voices side by side, before choosing one.

Each voice says the same six moments of a call, through the same pipeline as a real call (pace
per kind of line, read-back split, parts joined into one clip), so what you hear is what callers
will hear. Listen with the questions in VOICE_REVIEW.md in mind: does it sound like a calm, clear
person at a control room, or does it sound breathy, intimate or flat?

Run from flood-sos/backend with the venv active:
    python scripts\\voice_audition.py                       # default shortlist, Hindi and Telugu
    python scripts\\voice_audition.py --lang hi-IN          # one language
    python scripts\\voice_audition.py --voices timbre-v3.0:Kalpana,timbre-v2.5:Yashvi
    python scripts\\voice_audition.py --dry-run             # list what would be made

Files go to backend\\voice_audition\\<lang>\\<model>_<voice>\\ (git-ignored). Each new line costs
Timbre credits once; running it again is free.
"""
import argparse
import asyncio
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "app" imports work

import httpx  # noqa: E402

from app import phrases, prompts  # noqa: E402
from app.config import settings  # noqa: E402
from app.voice.call import speak  # noqa: E402
from app.voice.gnani_http import GnaniError  # noqa: E402
from app.voice.tts import TimbreTTS  # noqa: E402

# Shortlist from Gnani's voice catalog: warm but composed. Breathy "gentle" voices and
# expressive narration voices are left out on purpose. v3.0 voices speak every language.
DEFAULT_VOICES = {
    "hi-IN": ["timbre-v2.5:Yashvi", "timbre-v2.5:Ambuja", "timbre-v3.0:Kalpana",
              "timbre-v3.0:Tarika", "timbre-v3.0:Shivani"],
    "te-IN": ["timbre-v2.5:Lehara", "timbre-v2.5:Suhana", "timbre-v3.0:Kalpana",
              "timbre-v3.0:Tarika", "timbre-v3.0:Shivani"],
    "en-IN": ["timbre-v2.5:Shlok", "timbre-v3.0:Kalpana", "timbre-v3.0:Tarika"],
    "ta-IN": ["timbre-v2.5:Noopur", "timbre-v2.5:Brinda", "timbre-v3.0:Kalpana", "timbre-v3.0:Tarika"],
}

SAMPLE_DETAILS = {
    "hi-IN": "4 लोग, बड़े-बूढ़े के साथ, नेहरू स्ट्रीट, सैनिकपुरी, पिन कोड 5 0 0 0 9 4, ग्राउंड फ्लोर",
    "te-IN": "4 మంది, పెద్దవాళ్ళు తో కలిపి, నెహ్రూ స్ట్రీట్, సైనిక్‌పురి, పిన్ కోడ్ 5 0 0 0 9 4, గ్రౌండ్ ఫ్లోర్",
    "en-IN": "4 people, including elderly, at Nehru Street, Sainikpuri, pin code 5 0 0 0 9 4, ground floor",
    "ta-IN": "4 பேர், வயசானவங்க உட்பட, நேரு தெரு, சைனிக்புரி, பின் கோடு 5 0 0 0 9 4, தரை தளம்",
}


def moments(lang: str) -> list[tuple[str, list[str]]]:
    """(file name, reply parts) for six moments that need different delivery."""
    s = lambda key, **kw: phrases.say(key, lang, **kw)
    out = []
    if lang == prompts.GREETING["lang"]:
        out.append(("1_greeting", [prompts.GREETING["text"]]))
    out += [
        ("2_ack_then_question", [s("ack"), s("area1")]),
        ("3_panicking_caller", [s("calm"), s("danger2")]),
        ("4_urgent", [s("urgent"), s("p0_wait", digits="4 7 2 1")]),
        ("5_readback", [s("ack"), s("readback", details=SAMPLE_DETAILS[lang])]),
        ("6_close", [s("close", digits="4 7 2 1")]),
    ]
    return out


async def main(langs: list[str], voices_arg: str, dry_run: bool) -> int:
    out_root = Path("voice_audition")
    if not settings.gnani_api_key and not dry_run:
        print("GNANI_API_KEY is not set in .env")
        return 1
    async with httpx.AsyncClient(timeout=settings.gnani_timeout) as client:
        for lang in langs:
            candidates = voices_arg.split(",") if voices_arg else DEFAULT_VOICES.get(lang, [])
            for cand in candidates:
                model, voice = cand.split(":", 1)
                folder = out_root / lang / f"{model}_{voice}"
                tts = TimbreTTS(client, model=model, voices={lang: voice}, fallback_lang=lang)
                for name, parts in moments(lang):
                    if dry_run:
                        print(f"  {folder / name}.wav  <- {' | '.join(p[:40] for p in parts)}")
                        continue
                    try:
                        urls, ms, err = await speak(tts, parts, lang)
                    except GnaniError as e:
                        print(f"  {cand} {name}: FAILED {e}")
                        if e.status in (401, 402, 403):
                            return 1
                        continue
                    if err or len(urls) != 1:
                        print(f"  {cand} {name}: FAILED {err}")
                        continue
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy(Path(settings.tts_cache_dir) / urls[0].rsplit("/", 1)[1], folder / f"{name}.wav")
                    print(f"  {lang} {cand:22} {name:22} {ms} ms")
    if not dry_run:
        print(f"\nDone. Open {out_root.resolve()} and listen voice by voice, same moment across voices.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--lang", default="hi-IN,te-IN", help="comma-separated, e.g. hi-IN,te-IN")
    p.add_argument("--voices", default="", help="model:Voice,... (default: a shortlist per language)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.lang.split(","), a.voices, a.dry_run)))
