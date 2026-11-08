"""Generate audio for every fixed line in phrases.py (and the greeting) before the demo.

Run from flood-sos/backend with the venv active (the server doesn't need to be running):
    python scripts\\prewarm_voice.py            # all reply languages
    python scripts\\prewarm_voice.py --dry-run  # only list what would be generated

Run it again after changing phrases.py, TTS_VOICES or TTS_SPEED: only new lines cost credits.
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "app" imports work

import httpx  # noqa: E402

from app import prompts  # noqa: E402
from app.config import settings  # noqa: E402
from app.voice.call import fixed_lines  # noqa: E402
from app.voice.gnani_http import GnaniError  # noqa: E402
from app.voice.tts import TimbreTTS  # noqa: E402


async def main(dry_run: bool) -> int:
    langs = [lang for lang in settings.supported_reply_langs if lang in settings.tts_voices]
    missing = [lang for lang in settings.supported_reply_langs if lang not in settings.tts_voices]
    if missing:
        print(f"No voice set in TTS_VOICES for {', '.join(missing)}: those replies use the fallback voice.")
    lines = fixed_lines(langs, extra=[(prompts.GREETING["text"], prompts.GREETING["lang"])])

    async with httpx.AsyncClient(timeout=settings.gnani_timeout) as client:
        tts = TimbreTTS(client)
        todo = [(text, lang) for text, lang in lines if not tts.cached_path(text, lang).exists()]
        print(f"{len(lines)} fixed lines in {', '.join(langs)}: {len(lines) - len(todo)} cached, {len(todo)} to generate")
        if dry_run or not todo:
            for text, lang in todo:
                print(f"  {lang}  {text[:70]}")
            return 0
        if not settings.gnani_api_key:
            print("GNANI_API_KEY is not set in .env")
            return 1
        failed = 0
        for i, (text, lang) in enumerate(todo, 1):
            try:
                await tts.synthesize(text, lang)
                print(f"  [{i}/{len(todo)}] {lang} {tts.voice_for(lang)[1]:8} {text[:60]}")
            except GnaniError as e:
                failed += 1
                print(f"  [{i}/{len(todo)}] FAILED {lang}: {e}")
                if e.status in (401, 402, 403):
                    break  # wrong key / no credits: every line will fail the same way
        print(f"\nDone: {tts.api_calls} generated, {failed} failed. Cache: {Path(settings.tts_cache_dir).resolve()}")
        return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    sys.exit(asyncio.run(main(p.parse_args().dry_run)))