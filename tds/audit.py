"""Append-only JSONL audit trail: what went in, what the model saw and said,
which rule set computed the number, and what the human decided."""
import hashlib
import json
from datetime import datetime, timezone

from .config import AUDIT_DIR

LOG = AUDIT_DIR / "audit_log.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def write(event: str, payload: dict) -> str:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    record = {"ts": _now(), "event": event, **payload}
    record["record_id"] = fingerprint(record)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return record["record_id"]
