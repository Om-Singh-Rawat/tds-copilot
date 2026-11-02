"""End-to-end flow for one invoice:

  vendor master -> rule set by date -> retrieve sources -> classify lines (LLM or keyword)
  -> keyword cross-check -> deterministic engine -> router -> audit log
"""
import json
from datetime import date
from decimal import Decimal
from functools import lru_cache

from . import audit, baseline, classifier, config, engine, router
from .retrieval import core_definition_ids, load_kb, retrieve
from .rules import load_rule_sets, rule_set_for


@lru_cache(maxsize=1)
def vendors() -> dict:
    return json.loads(config.VENDORS_PATH.read_text(encoding="utf-8"))["vendors"]


@lru_cache(maxsize=1)
def ledger() -> list[dict]:
    return json.loads(config.LEDGER_PATH.read_text(encoding="utf-8"))["payments"]


def build_query(invoice: dict, vendor: dict | None) -> str:
    parts = [l["description"] for l in invoice["lines"]]
    if vendor:
        parts.append(vendor.get("nature_of_business", ""))
    return " ".join(parts)


def _engine_to_dict(res: engine.EngineResult | None) -> dict | None:
    if res is None:
        return None
    return {
        "rule_set_id": res.rule_set_id,
        "tds_total": int(res.tds_total),
        "flags": res.flags,
        "sections": [{
            "section": s.section, "base_this_invoice": str(s.base_this_invoice), "taxable": s.taxable,
            "tds_base": str(s.tds_base), "rate": str(s.rate), "tds": int(s.tds),
            "steps": s.steps, "flags": s.flags,
        } for s in res.sections],
    }


def process(invoice: dict, mode: str = "llm", samples: int = 1, model: str | None = None,
            override_codes: list[str] | None = None, chat_fn=None, write_audit: bool = True) -> dict:
    """mode: 'llm' (AI pipeline), 'baseline' (keywords only) or 'human' (override_codes given)."""
    vendor = vendors().get(invoice["vendor_id"])
    rs = rule_set_for(date.fromisoformat(invoice["date"]))
    retrieved = retrieve(build_query(invoice, vendor), config.RETRIEVAL_TOP_K,
                         pinned_ids=core_definition_ids(rs or load_rule_sets()[-1]))
    base_codes = baseline.classify(invoice)
    n = len(invoice["lines"])

    error, raw, prompt, used_model = None, None, None, None
    agreement = [1.0] * n
    if mode == "human":
        classifications = [{"line": i + 1, "code": c, "citations": [], "confidence": "high",
                            "ambiguity_flags": [], "reasoning": "set by reviewer", "nature_of_payment": ""}
                           for i, c in enumerate(override_codes)]
    elif mode == "baseline":
        classifications = [{"line": i + 1, "code": c or "UNSURE", "citations": [], "confidence": "high" if c else "low",
                            "ambiguity_flags": [], "reasoning": "keyword match" if c else "no single keyword match",
                            "nature_of_payment": ""} for i, c in enumerate(base_codes)]
    else:
        try:
            out = classifier.classify(invoice, vendor or {}, retrieved, samples=samples, model=model, chat_fn=chat_fn)
            classifications, agreement = out["lines"], out["agreement"]
            raw, prompt, used_model = out["raw"], out["prompt"], out["model"]
        except Exception as e:  # network, quota, or unparsable output -> human
            error = f"{type(e).__name__}: {e}"
            classifications = [{"line": i + 1, "code": "UNSURE", "citations": [], "confidence": "low",
                                "ambiguity_flags": [], "reasoning": "classifier unavailable",
                                "nature_of_payment": ""} for i in range(n)]

    codes = [c["code"] for c in classifications]
    eng = None
    if rs and vendor and vendor.get("resident", True):
        eng = engine.compute(invoice, codes, vendor, ledger(), rs)

    invoice_base = sum((engine.line_base(l, invoice.get("gst_shown_separately", True)) for l in invoice["lines"]), Decimal(0))
    route, reasons = router.decide(
        vendor, rs, classifications, retrieved,
        base_codes if mode == "llm" else [None] * n, agreement, eng,
        mode="llm" if mode == "llm" else "other", error=error, invoice_base=invoice_base,
    )
    if mode == "human":
        reasons = [r for r in reasons if r["code"] not in ("unsure",)]
        route = "human_decided"

    result = {
        "invoice": invoice,
        "vendor": vendor,
        "mode": mode,
        "model": used_model,
        "rule_set_id": rs["rule_set_id"] if rs else None,
        "kb_version": f"{load_kb()['kb_version']}#{load_kb()['_hash']}",
        "retrieved": [{"id": c["id"], "title": c["title"], "authority": c["authority"], "source": c["source"],
                       "applies_to": c["applies_to"], "score": c["score"], "pinned": c["pinned"],
                       "text": c["text"]} for c in retrieved],
        "classifications": classifications,
        "agreement": agreement,
        "baseline_codes": base_codes,
        "engine": _engine_to_dict(eng),
        # an undecided line means the total is unknown, not zero
        "tds_total": int(eng.tds_total) if eng and "UNSURE" not in codes else None,
        "route": route,
        "reasons": reasons,
        "error": error,
    }
    if write_audit:
        result["audit_id"] = audit.write("classification", {
            "invoice_fp": audit.fingerprint(invoice), "invoice_no": invoice.get("invoice_no"),
            "vendor_id": invoice["vendor_id"], "mode": mode, "model": used_model,
            "rule_set_id": result["rule_set_id"], "kb_version": result["kb_version"],
            "retrieved_ids": [c["id"] for c in retrieved], "prompt_fp": audit.fingerprint(prompt) if prompt else None,
            "raw_model_output": raw, "codes": codes, "tds_total": result["tds_total"],
            "route": route, "reasons": [r["code"] for r in reasons], "error": error,
        })
    return result
