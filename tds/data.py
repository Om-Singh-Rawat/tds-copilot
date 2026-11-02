"""Master-data access. The prototype reads synthetic JSON files; in production
these three functions are the seam where an ERP / database adapter plugs in."""
import json
from functools import lru_cache

from . import config


def _load(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def vendors() -> dict[str, dict]:
    return _load(config.VENDORS_PATH)["vendors"]


@lru_cache(maxsize=1)
def ledger() -> list[dict]:
    return _load(config.LEDGER_PATH)["payments"]


@lru_cache(maxsize=1)
def test_cases() -> list[dict]:
    return _load(config.TEST_CASES_PATH)["cases"]


def test_case(case_id: str) -> dict | None:
    return next((c for c in test_cases() if c["id"].upper() == case_id.upper()), None)
