"""LLM classifier: reads messy invoice text and proposes a TDS section per line.

The model's ONLY job is classification with citations. It never sees rates in a
way it is asked to apply, and it never outputs an amount - the engine does that.
"""
import json
import re
from collections import Counter

from . import llm
from .rules import all_codes

SYSTEM_PROMPT = """You are a TDS (Indian tax deducted at source) classification assistant used by an accounts team.
Your only job: for each invoice line, decide which TDS category applies to a payment made to a RESIDENT payee.

Rules you must follow:
1. Use ONLY the numbered SOURCES provided. Do not rely on memory for law. Cite the source ids you relied on.
2. Return exactly one code per line from the ALLOWED CODES list. Do not invent codes.
3. Do NOT calculate tax, rates or thresholds. Another system does that.
4. If the sources do not settle the question, or the description is too vague, return "UNSURE" and say what fact is missing.
5. If an invoice line combines different natures (e.g. goods + service in one amount), flag "mixed_supply".
6. Use the vendor's nature of business as context, but the line description decides.
7. Answer with a single JSON object and nothing else."""

OUTPUT_SCHEMA = """{
  "lines": [
    {
      "line": <line number starting at 1>,
      "nature_of_payment": "<5-12 word plain description>",
      "code": "<one ALLOWED CODE>",
      "citations": ["<source id>", "..."],
      "confidence": "high" | "medium" | "low",
      "ambiguity_flags": ["mixed_supply" | "reimbursement" | "vague_description" | "grey_area" | "other: <text>"],
      "reasoning": "<one or two sentences tying the description to the cited source>"
    }
  ]
}"""


def build_messages(invoice: dict, vendor: dict, sources: list[dict]) -> list[dict]:
    codes = "\n".join(f"- {c}: {t}" for c, t in all_codes().items())
    src = "\n\n".join(f"[{s['id']}] ({s['authority']}; {s['source']})\n{s['text']}" for s in sources)
    lines = "\n".join(
        f"{i}. \"{l['description']}\" (taxable value Rs {l['taxable_value']})"
        for i, l in enumerate(invoice["lines"], 1)
    )
    user = f"""ALLOWED CODES:
{codes}

SOURCES:
{src}

VENDOR: {vendor.get('name', 'unknown')} | nature of business: {vendor.get('nature_of_business') or 'not recorded'}

INVOICE LINES:
{lines}

Return JSON in this shape:
{OUTPUT_SCHEMA}"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def parse(content: str, n_lines: int) -> list[dict]:
    """Pull the JSON object out of the reply and validate it strictly."""
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    data = json.loads(m.group(0))
    valid = set(all_codes())
    out = []
    by_line = {int(x.get("line", i + 1)): x for i, x in enumerate(data.get("lines", []))}
    for i in range(1, n_lines + 1):
        x = by_line.get(i)
        if x is None:
            raise ValueError(f"model returned no answer for line {i}")
        code = str(x.get("code", "")).strip().upper()
        if code not in valid:
            raise ValueError(f"line {i}: invalid code '{code}'")
        out.append({
            "line": i,
            "nature_of_payment": x.get("nature_of_payment", ""),
            "code": code,
            "citations": [str(c) for c in x.get("citations", [])],
            "confidence": str(x.get("confidence", "low")).lower(),
            "ambiguity_flags": [str(f) for f in x.get("ambiguity_flags", []) if f],
            "reasoning": x.get("reasoning", ""),
        })
    return out


def classify(invoice: dict, vendor: dict, sources: list[dict], samples: int = 1,
             model: str | None = None, chat_fn=None) -> dict:
    """Returns {"lines": [...], "agreement": [...], "raw": [...], "model": str}.

    With samples > 1 the model is called several times at temperature 0.7 and the
    majority code wins; per-line agreement is reported so the router can treat a
    split vote as uncertainty (self-consistency is a better signal than the
    model's self-reported confidence).
    """
    chat_fn = chat_fn or llm.chat
    messages = build_messages(invoice, vendor, sources)
    temperature = 0.0 if samples == 1 else 0.7
    runs, raws, used_model = [], [], model
    for s in range(samples):
        reply = chat_fn(messages, model=model, temperature=temperature, sample_idx=s)
        raws.append(reply["content"])
        used_model = reply.get("model", used_model)
        runs.append(parse(reply["content"], len(invoice["lines"])))

    final, agreement = [], []
    for i in range(len(invoice["lines"])):
        code, n = Counter(r[i]["code"] for r in runs).most_common(1)[0]
        final.append(aggregate_line([r[i] for r in runs], code))
        agreement.append(n / samples)
    return {"lines": final, "agreement": agreement, "raw": raws, "model": used_model,
            "prompt": messages}


def aggregate_line(samples: list[dict], code: str) -> dict:
    """Merge one line's answers across samples.

    The first evaluation showed the code is stable across samples but the
    ambiguity flags are not, so a flag (and 'low' confidence) only counts when a
    majority of samples raise it. With one sample everything is kept (flags are
    reduced to their category, e.g. "other: ..." -> "other").
    """
    agreeing = [s for s in samples if s["code"] == code]
    majority = len(samples) / 2
    flag_votes = Counter(f for s in samples for f in dict.fromkeys(_flag_key(x) for x in s["ambiguity_flags"]))
    flags = [f for f, v in flag_votes.items() if v > majority]
    low_votes = sum(s["confidence"] == "low" for s in samples)
    confidence = "low" if low_votes > majority else Counter(s["confidence"] for s in agreeing).most_common(1)[0][0]
    if confidence == "low" and low_votes <= majority:
        confidence = "medium"
    citations = list(dict.fromkeys(c for s in agreeing for c in s["citations"]))
    return dict(agreeing[0], ambiguity_flags=flags, confidence=confidence, citations=citations)


def _flag_key(flag: str) -> str:
    # "other: free text" varies run to run; vote on the category only
    return flag.split(":", 1)[0].strip().lower()
