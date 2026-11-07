import os
import tempfile

# Tests always use the offline fake brain and a throwaway database.
os.environ["LLM_PROVIDER"] = "fake"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")