"""Decides whether a result may be auto-suggested or must go to a human reviewer.

Every check is deterministic and named, so the reviewer sees *why* an item was
routed to them. 'auto' still means "suggested" - the accountant who files the
TDS return remains accountable; 'auto' items can be batch-approved.
"""
from decimal import Decimal

from .engine import EngineResult

REVIEW, AUTO = "review", "auto"


def line_checks(i: int, cl: dict, retrieved: dict[str, dict], baseline_code: str | None,
                agreement: float, mode: str) -> list[dict]:
    reasons = []
    code = cl["code"]
    tag = f"line {i + 1}"

    if code == "UNSURE":
        reasons.append({"code": "unsure", "msg": f"{tag}: classifier could not decide - {cl.get('reasoning', '')}"})
        return reasons
    if code == "OUT_OF_SCOPE":
        reasons.append({"code": "out_of_scope", "msg": f"{tag}: payment type outside this system's scope"})

    if mode == "llm":
        grounded = [c for c in cl["citations"] if c in retrieved and code in retrieved[c]["applies_to"]]
        if not grounded:
            reasons.append({"code": "ungrounded_citation",
                            "msg": f"{tag}: no cited source both was retrieved and supports {code} (cited {cl['citations']})"})
        elif all(retrieved[c]["authority"] == "practice" for c in grounded):
            reasons.append({"code": "practice_only",
                            "msg": f"{tag}: {code} rests only on practice/judgment sources, not statute or circular"})
        if cl["confidence"] == "low":
            reasons.append({"code": "low_confidence", "msg": f"{tag}: model reported low confidence"})
        if cl["ambiguity_flags"]:
            reasons.append({"code": "ambiguity_flag", "msg": f"{tag}: model flagged {cl['ambiguity_flags']}"})
        if agreement < 1.0:
            reasons.append({"code": "split_vote", "msg": f"{tag}: only {agreement:.0%} of samples agreed"})
        if baseline_code and baseline_code != code:
            reasons.append({"code": "baseline_disagrees",
                            "msg": f"{tag}: keyword cross-check says {baseline_code}, model says {code}"})
    return reasons


def decide(vendor: dict | None, rule_set: dict | None, classifications: list[dict], retrieved: list[dict],
           baseline_codes: list[str | None], agreement: list[float], engine: EngineResult | None,
           mode: str, error: str | None = None, invoice_base: Decimal = Decimal(0)) -> tuple[str, list[dict]]:
    reasons: list[dict] = []
    if vendor is None:
        reasons.append({"code": "vendor_unknown", "msg": "vendor not found in vendor master"})
    elif not vendor.get("resident", True):
        reasons.append({"code": "non_resident", "msg": "payee is non-resident (s.195) - outside scope"})
    if rule_set is None:
        reasons.append({"code": "no_rule_set",
                        "msg": "no verified rule set covers this payment date - rates not computed"})
    if error:
        reasons.append({"code": "classifier_error", "msg": f"classifier failed: {error}"})

    by_id = {c["id"]: c for c in retrieved}
    for i, cl in enumerate(classifications):
        reasons += line_checks(i, cl, by_id, baseline_codes[i], agreement[i], mode)

    if engine:
        if "no_pan_206AA" in engine.flags:
            reasons.append({"code": "no_pan", "msg": "PAN missing/inoperative - 20% rate applied under s.206AA; request PAN"})
        if "catch_up_on_prior_payments" in engine.flags:
            reasons.append({"code": "catch_up", "msg": "annual limit crossed - deduction includes earlier untaxed payments"})
    if rule_set and invoice_base > Decimal(str(rule_set["high_value_review_threshold"])):
        reasons.append({"code": "high_value", "msg": f"invoice base {invoice_base} above materiality limit"})

    return (REVIEW if reasons else AUTO), reasons
