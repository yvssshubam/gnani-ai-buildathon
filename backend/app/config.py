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


settings = Settings()