import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RULES_DIR = DATA / "rules"
KB_PATH = DATA / "knowledge" / "kb.json"
VENDORS_PATH = DATA / "vendors.json"
LEDGER_PATH = DATA / "ledger.json"
TEST_CASES_PATH = DATA / "test_cases.json"
AUDIT_DIR = ROOT / "audit"
CACHE_DIR = ROOT / ".cache" / "llm"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader so the project needs no third-party packages."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "5"))
