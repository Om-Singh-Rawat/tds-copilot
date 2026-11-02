"""PAN checks. The 4th character of a PAN encodes the holder type, which decides
the s.194C rate (1% individual/HUF, 2% others) - so this is code, not AI."""
import re

PAN_RE = re.compile(r"^[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z]$")

HOLDER_TYPES = {
    "P": "individual", "H": "huf", "C": "company", "F": "firm",
    "A": "aop", "B": "boi", "G": "government", "J": "artificial_juridical_person",
    "L": "local_authority", "T": "trust",
}


def is_valid(pan: str | None) -> bool:
    return bool(pan) and bool(PAN_RE.match(pan))


def holder_type(pan: str | None) -> str | None:
    return HOLDER_TYPES.get(pan[3]) if is_valid(pan) else None
