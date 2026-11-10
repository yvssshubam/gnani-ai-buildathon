import os
import tempfile

# Tests always use the offline fake brain and a throwaway database.
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
# Notes run straight away in tests (on a live line they wait up to 20 s between runs).
os.environ["NOTES_MIN_GAP_SECONDS"] = "0"
# No internet in tests: areas off the map list are not looked up.
os.environ["GEOCODE_ENABLED"] = "0"
# Tests never depend on what is in your .env: a fixed model name (the gpt-oss reasoning rule keys
# on the name), and no second endpoint, so a failing fake server can never reach a real API.
os.environ["LLM_MODEL"] = "test-model"
os.environ["LLM_REASONING_EFFORT"] = ""
for _name in ("LLM_EXTRA_BODY", "LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_API_KEY", "LLM_FALLBACK_MODEL",
              "LLM_FALLBACK_NOTES_MODEL", "NOTES_LLM_BASE_URL", "NOTES_LLM_API_KEY", "NOTES_LLM_EXTRA_BODY"):
    os.environ[_name] = ""