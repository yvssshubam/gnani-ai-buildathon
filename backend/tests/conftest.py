import os
import tempfile

# Tests always use the offline fake brain and a throwaway database.
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
# Notes run straight away in tests (on a live line they wait up to 20 s between runs).
os.environ["NOTES_MIN_GAP_SECONDS"] = "0"
# No internet in tests: areas off the map list are not looked up.
os.environ["GEOCODE_ENABLED"] = "0"