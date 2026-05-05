import os
from pathlib import Path


TEST_DB = Path("/private/tmp/agenteval_test.db")
os.environ["AGENTEVAL_DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("OPENAI_API_KEY", None)
