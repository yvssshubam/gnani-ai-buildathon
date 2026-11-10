"""Settings read from environment variables (and an optional .env file)."""
import json
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so we don't need an extra dependency."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _json_env(name: str) -> dict:
    """A JSON object from an environment variable ({} when unset or not a JSON object)."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "fake")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))
    # For reasoning models (e.g. gpt-oss on Groq): "low" keeps replies fast. Leave empty for other models.
    llm_reasoning_effort: str = os.getenv("LLM_REASONING_EFFORT", "").strip()
    # Reasoning tokens count toward this limit, so keep it generous.
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    # The per-turn extract. Groq counts prompt + max_tokens against the tokens-per-minute limit
    # (8,000 on the free tier for gpt-oss), so a smaller allowance means more turns a minute.
    llm_extract_max_tokens: int = int(os.getenv("LLM_EXTRACT_MAX_TOKENS", "500"))
    # Free tier: Groq's limits are per model. Call notes and the demo's simulated caller run on a
    # second model, so the live extract keeps its model's 8,000 tokens a minute to itself.
    notes_llm_model: str = os.getenv("NOTES_LLM_MODEL", "openai/gpt-oss-120b")
    # Background call notes run at most this often per call, leaving the rate limit to live calls.
    notes_min_gap_seconds: float = float(os.getenv("NOTES_MIN_GAP_SECONDS", "20"))
    # Notes write a summary and translate every caller line: the model needs room (its reasoning counts too)
    notes_max_tokens: int = int(os.getenv("NOTES_MAX_TOKENS", "3000"))

    # --- Running on your own model server (e.g. Gnani Evon v3.3 behind Ollama or llama.cpp) ---
    # Extra fields added to every request to LLM_BASE_URL, as JSON. Use it for switches a server
    # needs that Groq doesn't, e.g. {"chat_template_kwargs": {"enable_thinking": false}}.
    llm_extra_body: dict = _json_env("LLM_EXTRA_BODY")
    # A second endpoint that answers when the first one can't (the notebook serving Evon stopped,
    # a timeout, a rate limit). Leave empty for no fallback.
    llm_fallback_base_url: str = os.getenv("LLM_FALLBACK_BASE_URL", "").strip()
    llm_fallback_api_key: str = os.getenv("LLM_FALLBACK_API_KEY", "").strip()
    llm_fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "").strip()
    # The fallback's model for notes and the simulated caller (default: LLM_FALLBACK_MODEL).
    llm_fallback_notes_model: str = os.getenv("LLM_FALLBACK_NOTES_MODEL", "").strip()
    # After the first endpoint is unreachable, go straight to the fallback for this long, so only
    # one caller turn pays for the timeout.
    llm_fallback_cooldown: float = float(os.getenv("LLM_FALLBACK_COOLDOWN_SECONDS", "60"))
    # Notes and the simulated caller can run on their own endpoint (e.g. Evon for notes only,
    # while the live call stays where it is). Empty = the same endpoint as the live call.
    notes_llm_base_url: str = os.getenv("NOTES_LLM_BASE_URL", "").strip()
    notes_llm_api_key: str = os.getenv("NOTES_LLM_API_KEY", "").strip()
    notes_llm_extra_body: dict = _json_env("NOTES_LLM_EXTRA_BODY")
    # Notes run in the background, so they can wait longer than a live turn. A self-hosted model
    # writing a long summary needs it (try 90). Default: the same as LLM_TIMEOUT_SECONDS.
    notes_llm_timeout: float = float(os.getenv("NOTES_LLM_TIMEOUT_SECONDS", os.getenv("LLM_TIMEOUT_SECONDS", "8")))
    # An area not on our map list ("Sainikpuri", a PIN code) is placed with OpenStreetMap's free
    # address search (Nominatim: at most one request a second, no key). GEOCODE_ENABLED=0 turns it off.
    geocode_enabled: bool = os.getenv("GEOCODE_ENABLED", "1").strip() not in ("0", "false", "no", "")
    geocode_url: str = os.getenv("GEOCODE_URL", "https://nominatim.openstreetmap.org/search")
    geocode_user_agent: str = os.getenv("GEOCODE_USER_AGENT", "Surgeline-flood-SOS-demo/1.0")
    geocode_timeout: float = float(os.getenv("GEOCODE_TIMEOUT_SECONDS", "6"))

    supported_reply_langs: list[str] = [
        x.strip() for x in os.getenv("SUPPORTED_REPLY_LANGS", "ta-IN,en-IN,hi-IN,te-IN").split(",") if x.strip()
    ]
    fallback_reply_lang: str = os.getenv("FALLBACK_REPLY_LANG", "hi-IN")

    max_turns: int = int(os.getenv("MAX_TURNS", "10"))
    db_path: str = os.getenv("DB_PATH", "flood_sos.db")

    # --- Gnani voice (Phase 2) ---
    gnani_api_key: str = os.getenv("GNANI_API_KEY", "").strip()
    gnani_base_url: str = os.getenv("GNANI_BASE_URL", "https://api.vachana.ai")
    gnani_timeout: float = float(os.getenv("GNANI_TIMEOUT_SECONDS", "15"))

    # Prisma v3.0 REST: one request per caller turn. Languages are hints, not a lock (max 4).
    stt_model: str = os.getenv("STT_MODEL", "prisma-v3.0")
    stt_languages: str = os.getenv("STT_LANGUAGES", "hi-IN,en-IN,ta-IN,te-IN")
    stt_format: str = os.getenv("STT_FORMAT", "codemix")
    # Context sent with each caller turn: "question_en" (the agent's last question, in English)
    # or "none".
    stt_context: str = os.getenv("STT_CONTEXT", "question_en").strip().lower()

    # Timbre v2.5. One voice per reply language: "lang:Voice,lang:Voice".
    tts_model: str = os.getenv("TTS_MODEL", "timbre-v2.5")
    tts_voices: dict[str, str] = dict(
        pair.split(":", 1) for pair in
        os.getenv("TTS_VOICES", "ta-IN:Noopur,hi-IN:Yashvi,te-IN:Lehara,en-IN:Shlok").split(",")
        if ":" in pair
    )
    tts_sample_rate: int = int(os.getenv("TTS_SAMPLE_RATE", "16000"))
    tts_speed: float = float(os.getenv("TTS_SPEED", "1.0"))
    tts_cache_dir: str = os.getenv("TTS_CACHE_DIR", "tts_cache")
    # Pace per kind of line, as a factor on TTS_SPEED (see app/voice/delivery.py).
    tts_pace: str = os.getenv("TTS_PACE", "plain:1.0,steady:0.95,brisk:1.05,readback:0.9")
    # Timbre v3.0 only: an audio tag per kind of line, e.g. "readback:<slow>". Empty = no tags.
    tts_tags: str = os.getenv("TTS_TAGS", "")
    # The parts of one reply are joined into one clip with this much silence between them
    # (half of it after a short "Okay."). TTS_STITCH=0 plays the parts as separate clips, as before.
    tts_gap_ms: int = int(os.getenv("TTS_GAP_MS", "280"))
    tts_stitch: bool = os.getenv("TTS_STITCH", "1").strip() not in ("0", "false", "no", "")

    # Simulated callers (demo): a different voice from the agent's, per language. Their own model,
    # so the agent can move to Timbre v3.0 while the caller voices stay on v2.5.
    sim_caller_tts_model: str = os.getenv("SIM_CALLER_TTS_MODEL", "timbre-v2.5")
    sim_caller_voices: dict[str, str] = dict(
        pair.split(":", 1) for pair in
        os.getenv("SIM_CALLER_VOICES", "hi-IN:Chitra,ta-IN:Trisha,te-IN:Lavanya,en-IN:Trupti").split(",")
        if ":" in pair
    )


settings = Settings()