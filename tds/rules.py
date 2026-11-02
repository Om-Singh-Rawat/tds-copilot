"""Versioned rule sets. Rates and thresholds live in JSON files, never in the model.

Each file declares the dates it is valid for. A payment dated outside every
loaded rule set gets no tax computation at all - it goes to a human.
"""
import json
from datetime import date
from functools import lru_cache

from .config import RULES_DIR


@lru_cache(maxsize=1)
def load_rule_sets() -> list[dict]:
    sets = []
    for path in sorted(RULES_DIR.glob("*.json")):
        rs = json.loads(path.read_text(encoding="utf-8"))
        rs["_file"] = path.name
        sets.append(rs)
    return sets


def rule_set_for(payment_date: date) -> dict | None:
    for rs in load_rule_sets():
        if date.fromisoformat(rs["valid_from"]) <= payment_date <= date.fromisoformat(rs["valid_to"]):
            return rs
    return None


def all_codes(rs: dict | None = None) -> dict[str, str]:
    """Every classification code the model may return, with a one-line meaning."""
    rs = rs or load_rule_sets()[-1]
    codes = {code: s["title"] for code, s in rs["sections"].items()}
    codes.update(rs["non_tds_codes"])
    return codes


def financial_year(d: date) -> str:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{str(start + 1)[-2:]}"
