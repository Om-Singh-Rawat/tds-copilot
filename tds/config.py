import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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

# Locations can be overridden so the package also works when installed or containerised.
DATA = Path(os.environ.get("TDS_DATA_DIR", ROOT / "data"))
RULES_DIR = DATA / "rules"
KB_PATH = Path(os.environ.get("TDS_KB_PATH", DATA / "knowledge" / "kb.json"))  # archived versions: data/knowledge/archive/
VENDORS_PATH = DATA / "vendors.json"
LEDGER_PATH = DATA / "ledger.json"
TEST_CASES_PATH = DATA / "test_cases.json"
AUDIT_DIR = Path(os.environ.get("TDS_AUDIT_DIR", ROOT / "audit"))
CACHE_DIR = Path(os.environ.get("TDS_CACHE_DIR", ROOT / ".cache" / "llm"))

def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
RETRIEVAL_TOP_K = int(os.environ.get("RETRIEVAL_TOP_K", "5"))

# Web server. Defaults are safe for a laptop; set TDS_PUBLIC=1 when exposing it on the internet.
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
PUBLIC_MODE = _flag("TDS_PUBLIC", False)              # hides the audit trail from visitors
LIVE_LLM = _flag("TDS_LIVE_LLM", True)                # False = serve cached LLM answers only (no spend)
LLM_REQUESTS_PER_MINUTE = int(os.environ.get("TDS_LLM_RPM", "6"))  # per client IP, live LLM calls only
MAX_BODY_BYTES = 64 * 1024
