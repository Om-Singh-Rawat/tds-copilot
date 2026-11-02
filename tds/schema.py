"""Input validation for invoices arriving from the CLI, the web API or an ERP.

Rejecting malformed input up front keeps the engine's arithmetic honest and
stops oversized text from reaching the model (cost and prompt-injection surface).
"""
from datetime import date

MAX_LINES = 50
MAX_DESCRIPTION = 500
MAX_AMOUNT = 10_000_000_000  # Rs 1,000 crore per line


class InvalidInvoice(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _amount(value, field: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
    elif not 0 <= value <= MAX_AMOUNT:
        errors.append(f"{field} must be between 0 and {MAX_AMOUNT}")


def validate_invoice(inv) -> dict:
    """Return a normalised copy of the invoice or raise InvalidInvoice listing every problem."""
    errors: list[str] = []
    if not isinstance(inv, dict):
        raise InvalidInvoice(["invoice must be a JSON object"])

    if not isinstance(inv.get("vendor_id"), str) or not inv["vendor_id"].strip():
        errors.append("vendor_id is required")
    try:
        date.fromisoformat(str(inv.get("date")))
    except ValueError:
        errors.append("date must be YYYY-MM-DD")
    if "invoice_no" in inv and (not isinstance(inv["invoice_no"], str) or len(inv["invoice_no"]) > 64):
        errors.append("invoice_no must be a string of at most 64 characters")
    if not isinstance(inv.get("gst_shown_separately", True), bool):
        errors.append("gst_shown_separately must be true or false")
    pm = inv.get("period_months", 1)
    if isinstance(pm, bool) or not isinstance(pm, int) or not 1 <= pm <= 120:
        errors.append("period_months must be an integer from 1 to 120")

    lines = inv.get("lines")
    if not isinstance(lines, list) or not lines:
        errors.append("lines must be a non-empty list")
        lines = []
    elif len(lines) > MAX_LINES:
        errors.append(f"at most {MAX_LINES} lines per invoice")
    for i, line in enumerate(lines[:MAX_LINES], 1):
        if not isinstance(line, dict):
            errors.append(f"line {i} must be an object")
            continue
        desc = line.get("description")
        if not isinstance(desc, str) or not desc.strip():
            errors.append(f"line {i}: description is required")
        elif len(desc) > MAX_DESCRIPTION:
            errors.append(f"line {i}: description longer than {MAX_DESCRIPTION} characters")
        _amount(line.get("taxable_value"), f"line {i}: taxable_value", errors)
        _amount(line.get("gst", 0), f"line {i}: gst", errors)

    if errors:
        raise InvalidInvoice(errors)

    return {
        "vendor_id": inv["vendor_id"].strip(),
        "invoice_no": inv.get("invoice_no", ""),
        "date": str(inv["date"]),
        "gst_shown_separately": inv.get("gst_shown_separately", True),
        "period_months": pm,
        "lines": [{"description": l["description"].strip(), "taxable_value": l["taxable_value"],
                   "gst": l.get("gst", 0)} for l in lines],
    }
