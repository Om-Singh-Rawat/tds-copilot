"""Deterministic TDS calculator.

Given a section code per invoice line (decided upstream by the classifier or a
human), this computes the TDS base, rate, threshold test and amount. No AI
here: every number is reproducible and every step is written to `steps` so an
auditor can follow it.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from . import pan as pan_utils
from .rules import financial_year

NON_TAX_CODES = {"NO_TDS", "OUT_OF_SCOPE", "UNSURE"}


@dataclass
class SectionCalc:
    section: str
    base_this_invoice: Decimal
    taxable: bool
    tds_base: Decimal
    rate: Decimal
    tds: Decimal
    steps: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class EngineResult:
    rule_set_id: str
    sections: list[SectionCalc]
    tds_total: Decimal
    flags: list[str]


def _d(x) -> Decimal:
    return Decimal(str(x))


def _round(amount: Decimal) -> Decimal:
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def line_base(line: dict, gst_shown_separately: bool) -> Decimal:
    # CBDT Circular 23/2017: exclude GST where it is shown separately.
    taxable = _d(line["taxable_value"])
    return taxable if gst_shown_separately else taxable + _d(line.get("gst", 0))


def prior_payments(ledger: list[dict], vendor_id: str, section: str, before: date) -> list[dict]:
    fy = financial_year(before)
    return [
        p for p in ledger
        if p["vendor_id"] == vendor_id and p["section"] == section
        and financial_year(date.fromisoformat(p["date"])) == fy
        and date.fromisoformat(p["date"]) < before
    ]


def select_rate(section: str, spec: dict, vendor: dict, rs: dict, steps: list[str], flags: list[str]) -> Decimal:
    pan = vendor.get("pan")
    holder = pan_utils.holder_type(pan)
    rates = spec["rates"]
    base_rate = _d(rates.get(holder, rates["default"])) if holder else _d(rates["default"])
    if holder:
        steps.append(f"PAN {pan} -> holder type '{holder}' -> section rate {base_rate}%")
    if not pan_utils.is_valid(pan) or not vendor.get("pan_operative", False):
        reason = "PAN not furnished/invalid" if not pan_utils.is_valid(pan) else "PAN inoperative"
        floor = _d(rs["no_pan_rule"]["min_rate"])
        rate = max(base_rate, floor)
        steps.append(f"{reason} -> s.206AA: higher of {base_rate}% and {floor}% = {rate}%")
        flags.append("no_pan_206AA")
        return rate
    return base_rate


def threshold_test(section: str, spec: dict, base: Decimal, priors: list[dict],
                   period_months: int, steps: list[str], flags: list[str]) -> tuple[bool, Decimal]:
    """Returns (taxable, tds_base). tds_base may include earlier untaxed payments
    when an annual aggregate limit is crossed by this invoice."""
    th = spec["threshold"]
    prior_total = sum((_d(p["base"]) for p in priors), Decimal(0))
    prior_untaxed = sum((_d(p["base"]) for p in priors if not p["tds_deducted"]), Decimal(0))
    kind = th["type"]

    if kind == "none":
        steps.append("No threshold for this section")
        return True, base

    if kind == "monthly":
        months = max(int(period_months or 1), 1)
        per_month = base / months
        limit = _d(th["monthly"])
        steps.append(f"Rent per month = {base} / {months} = {per_month:.2f}; limit {limit} per month")
        return (per_month > limit), base

    aggregate_limit = _d(th["aggregate"])
    new_total = prior_total + base
    steps.append(f"FY aggregate before this invoice = {prior_total}; after = {new_total}; limit {aggregate_limit}")

    if kind == "single_or_aggregate":
        single_limit = _d(th["single"])
        if new_total > aggregate_limit:
            if prior_untaxed > 0:
                flags.append("catch_up_on_prior_payments")
                steps.append(f"Aggregate limit crossed -> deduct on this invoice plus {prior_untaxed} of earlier untaxed payments")
                return True, base + prior_untaxed
            steps.append("Aggregate limit already crossed -> taxable")
            return True, base
        if base > single_limit:
            steps.append(f"Single payment {base} exceeds {single_limit} -> taxable")
            return True, base
        steps.append(f"Single payment {base} <= {single_limit} and aggregate <= {aggregate_limit} -> no deduction")
        return False, base

    if kind == "aggregate":
        if new_total > aggregate_limit:
            if prior_untaxed > 0:
                flags.append("catch_up_on_prior_payments")
                steps.append(f"Aggregate limit crossed -> deduct on this invoice plus {prior_untaxed} of earlier untaxed payments")
                return True, base + prior_untaxed
            steps.append("Aggregate limit exceeded -> taxable")
            return True, base
        steps.append("Aggregate within limit -> no deduction")
        return False, base

    raise ValueError(f"Unknown threshold type {kind}")


def compute(invoice: dict, line_sections: list[str], vendor: dict, ledger: list[dict], rs: dict) -> EngineResult:
    pay_date = date.fromisoformat(invoice["date"])
    gst_sep = invoice.get("gst_shown_separately", True)

    grouped: dict[str, Decimal] = {}
    for line, code in zip(invoice["lines"], line_sections):
        if code in NON_TAX_CODES:
            continue
        grouped[code] = grouped.get(code, Decimal(0)) + line_base(line, gst_sep)

    results, all_flags = [], []
    for code, base in grouped.items():
        spec = rs["sections"][code]
        steps, flags = [], []
        steps.append(f"Section {code} ({spec['title']}), rule set {rs['rule_set_id']}")
        steps.append(f"Base on this invoice = {base} ({'excl.' if gst_sep else 'incl.'} GST)")

        if code == "194C" and spec.get("transporter_exemption") and vendor.get("transporter_declaration_194C6") \
                and pan_utils.is_valid(vendor.get("pan")) and vendor.get("pan_operative"):
            steps.append("Transporter declaration under s.194C(6) on file with valid PAN -> no deduction")
            flags.append("transporter_exemption_194C6")
            results.append(SectionCalc(code, base, False, base, Decimal(0), Decimal(0), steps, flags))
            all_flags += flags
            continue

        priors = prior_payments(ledger, invoice["vendor_id"], code, pay_date)
        taxable, tds_base = threshold_test(code, spec, base, priors, invoice.get("period_months", 1), steps, flags)
        rate = select_rate(code, spec, vendor, rs, steps, flags)
        tds = _round(tds_base * rate / 100) if taxable else Decimal(0)
        steps.append(f"TDS = {tds_base} x {rate}% = {tds}" if taxable else "TDS = 0")
        results.append(SectionCalc(code, base, taxable, tds_base, rate, tds, steps, flags))
        all_flags += flags

    total = sum((r.tds for r in results), Decimal(0))
    return EngineResult(rs["rule_set_id"], results, total, sorted(set(all_flags)))
