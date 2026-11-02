"""Keyword baseline - the 'simpler, non-AI approach' the assignment asks us to compare against.

It is used in two ways:
  1. as a stand-alone classifier in the evaluation, to show where keyword rules break;
  2. as an independent cross-check in the AI pipeline: if it confidently disagrees
     with the model, the line goes to a human.
Returns a code only when exactly one section's keywords match; otherwise None.
"""
KEYWORDS: dict[str, list[str]] = {
    "194J_DIRECTOR": ["sitting fee", "director"],
    "194H": ["commission", "brokerage"],
    "194I_A": ["dg set", "generator", "machine rent", "equipment rent", "crane hire"],
    "194I_B": ["rent for office", "office premises", "premises rent", "lease rent", "warehouse rent"],
    "194J_A": ["technical service", "technical support", "managed", "call centre"],
    "194J_B": ["legal", "professional fee", "professional charges", "audit fee", "advocate",
               "architect", "advertis", "interior", "consult"],
    "194C": ["contract", "labour", "housekeeping", "security guard", "catering", "freight",
             "transport", "manpower", "installation", "printing", "repair", "maintenance"],
    "NO_TDS": ["supply of", "purchase of", "cartridge", "paper", "stationery", "electricity"],
}


def classify_line(description: str) -> str | None:
    text = description.lower()
    hits = {code for code, words in KEYWORDS.items() if any(w in text for w in words)}
    return hits.pop() if len(hits) == 1 else None


def classify(invoice: dict) -> list[str | None]:
    return [classify_line(line["description"]) for line in invoice["lines"]]
