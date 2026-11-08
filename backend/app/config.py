"""Settings read from environment variables (and an optional .env file)."""
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

    # Simulated callers (demo): a different voice from the agent's, per language.
    sim_caller_voices: dict[str, str] = dict(
        pair.split(":", 1) for pair in
        os.getenv("SIM_CALLER_VOICES", "hi-IN:Chitra,ta-IN:Trisha,te-IN:Lavanya,en-IN:Trupti").split(",")
        if ":" in pair
    )


settings = Settings()