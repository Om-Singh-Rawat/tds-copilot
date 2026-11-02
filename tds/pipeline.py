"""End-to-end flow for one invoice:

  validate -> vendor master -> rule set by date -> retrieve sources
  -> classify lines (LLM, keyword baseline, or a human override)
  -> keyword cross-check -> deterministic engine -> router -> audit log
"""
from datetime import date
from decimal import Decimal

from . import audit, baseline, classifier, config, data, engine, router
from .retrieval import core_definition_ids, load_kb, retrieve
from .rules import all_codes, load_rule_sets, rule_set_for
from .schema import InvalidInvoice, validate_invoice

MODES = ("llm", "baseline", "human")


def build_query(invoice: dict, vendor: dict | None) -> str:
    parts = [l["description"] for l in invoice["lines"]]
    if vendor:
        parts.append(vendor.get("nature_of_business", ""))
    return " ".join(parts)


def _placeholder(n: int, code_for, reasoning_for, confidence_for) -> list[dict]:
    return [{"line": i + 1, "code": code_for(i), "citations": [], "confidence": confidence_for(i),
             "ambiguity_flags": [], "reasoning": reasoning_for(i), "nature_of_payment": ""} for i in range(n)]


def _classify(invoice, vendor, retrieved, base_codes, mode, samples, model, override_codes, chat_fn) -> dict:
    """Returns classifications plus whatever the LLM produced (for the audit log)."""
    n = len(invoice["lines"])
    out = {"agreement": [1.0] * n, "error": None, "raw": None, "prompt": None, "model": None}
    if mode == "human":
        out["lines"] = _placeholder(n, lambda i: override_codes[i], lambda i: "set by reviewer", lambda i: "high")
    elif mode == "baseline":
        out["lines"] = _placeholder(
            n, lambda i: base_codes[i] or "UNSURE",
            lambda i: "keyword match" if base_codes[i] else "no single keyword match",
            lambda i: "high" if base_codes[i] else "low")
    else:
        try:
            res = classifier.classify(invoice, vendor or {}, retrieved, samples=samples, model=model, chat_fn=chat_fn)
            out.update(lines=res["lines"], agreement=res["agreement"], raw=res["raw"],
                       prompt=res["prompt"], model=res["model"])
        except Exception as e:  # network, quota or unparsable output -> human
            out["error"] = f"{type(e).__name__}: {e}"
            out["lines"] = _placeholder(n, lambda i: "UNSURE", lambda i: "classifier unavailable", lambda i: "low")
    return out


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
    """Run one invoice. mode: 'llm' (AI pipeline), 'baseline' (keywords only) or 'human' (override_codes)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    invoice = validate_invoice(invoice)
    n = len(invoice["lines"])
    if mode == "human":
        if not override_codes or len(override_codes) != n or any(c not in all_codes() for c in override_codes):
            raise InvalidInvoice([f"override_codes must give one valid code for each of the {n} lines"])
    samples = max(1, min(int(samples), 5))

    vendor = data.vendors().get(invoice["vendor_id"])
    rs = rule_set_for(date.fromisoformat(invoice["date"]))
    retrieved = retrieve(build_query(invoice, vendor), config.RETRIEVAL_TOP_K,
                         pinned_ids=core_definition_ids(rs or load_rule_sets()[-1]))
    base_codes = baseline.classify(invoice)

    cl = _classify(invoice, vendor, retrieved, base_codes, mode, samples, model, override_codes, chat_fn)
    classifications = cl["lines"]
    codes = [c["code"] for c in classifications]

    eng = None
    if rs and vendor and vendor.get("resident", True):
        eng = engine.compute(invoice, codes, vendor, data.ledger(), rs)

    invoice_base = sum((engine.line_base(l, invoice["gst_shown_separately"]) for l in invoice["lines"]), Decimal(0))
    route, reasons = router.decide(
        vendor, rs, classifications, retrieved,
        base_codes if mode == "llm" else [None] * n, cl["agreement"], eng,
        mode="llm" if mode == "llm" else "other", error=cl["error"], invoice_base=invoice_base,
    )
    if mode == "human":
        route = "human_decided"

    kb = load_kb()
    result = {
        "invoice": invoice,
        "vendor": vendor,
        "mode": mode,
        "model": cl["model"],
        "rule_set_id": rs["rule_set_id"] if rs else None,
        "kb_version": f"{kb['kb_version']}#{kb['_hash']}",
        "retrieved": [{k: c[k] for k in ("id", "title", "authority", "source", "applies_to", "score", "pinned", "text")}
                      for c in retrieved],
        "classifications": classifications,
        "agreement": cl["agreement"],
        "baseline_codes": base_codes,
        "engine": _engine_to_dict(eng),
        # an undecided line means the total is unknown, not zero
        "tds_total": int(eng.tds_total) if eng and "UNSURE" not in codes else None,
        "route": route,
        "reasons": reasons,
        "error": cl["error"],
    }
    if write_audit:
        result["audit_id"] = audit.write("classification", {
            "invoice_fp": audit.fingerprint(invoice), "invoice_no": invoice.get("invoice_no"),
            "vendor_id": invoice["vendor_id"], "mode": mode, "model": cl["model"],
            "rule_set_id": result["rule_set_id"], "kb_version": result["kb_version"],
            "retrieved_ids": [c["id"] for c in retrieved],
            "prompt_fp": audit.fingerprint(cl["prompt"]) if cl["prompt"] else None,
            "raw_model_output": cl["raw"], "codes": codes, "tds_total": result["tds_total"],
            "route": route, "reasons": [r["code"] for r in reasons], "error": cl["error"],
        })
    return result
