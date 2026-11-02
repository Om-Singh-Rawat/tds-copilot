import unittest
from datetime import date

from tds import data, engine, pan
from tds.rules import financial_year, rule_set_for

CASES = {c["id"]: c for c in data.test_cases()}
RS = rule_set_for(date(2025, 6, 1))


def run(case_id, codes=None, vendor_patch=None, invoice_patch=None):
    inv = dict(CASES[case_id]["invoice"], **(invoice_patch or {}))
    v = dict(data.vendors()[inv["vendor_id"]], **(vendor_patch or {}))
    return engine.compute(inv, codes or CASES[case_id]["expected"]["lines"], v, data.ledger(), RS)


class RuleSetTests(unittest.TestCase):
    def test_rule_set_window(self):
        self.assertIsNotNone(rule_set_for(date(2025, 4, 1)))
        self.assertIsNotNone(rule_set_for(date(2026, 3, 31)))
        self.assertIsNone(rule_set_for(date(2026, 4, 1)), "no unverified rules may be applied after FY 2025-26")

    def test_financial_year(self):
        self.assertEqual(financial_year(date(2025, 4, 1)), "2025-26")
        self.assertEqual(financial_year(date(2026, 3, 31)), "2025-26")
        self.assertEqual(financial_year(date(2025, 3, 31)), "2024-25")


class PanTests(unittest.TestCase):
    def test_holder_types(self):
        self.assertEqual(pan.holder_type("AJMPI7342Q"), "individual")
        self.assertEqual(pan.holder_type("AAKCS4821M"), "company")
        self.assertEqual(pan.holder_type("AAQFP2290L"), "firm")
        self.assertIsNone(pan.holder_type("BAD"))
        self.assertIsNone(pan.holder_type(None))


class EngineTests(unittest.TestCase):
    def test_every_case_with_expected_amount(self):
        """The engine, given the correct sections, must reproduce every hand-computed expected TDS."""
        for cid, c in CASES.items():
            exp = c["expected"]
            inv = c["invoice"]
            if exp["tds_total"] is None or rule_set_for(date.fromisoformat(inv["date"])) is None:
                continue
            with self.subTest(case=cid):
                self.assertEqual(int(run(cid).tds_total), exp["tds_total"])

    def test_194c_individual_rate_is_1pct(self):
        r = run("T01", vendor_patch={"pan": "ABCPS1234K"})
        self.assertEqual(int(r.tds_total), 1200)

    def test_gst_included_when_not_shown_separately(self):
        r = run("T01", invoice_patch={"gst_shown_separately": False})
        self.assertEqual(int(r.tds_total), 2832)  # 2% of 1,41,600

    def test_catch_up_flag(self):
        r = run("T16")
        self.assertIn("catch_up_on_prior_payments", r.flags)
        self.assertEqual(r.sections[0].tds_base, 102000)

    def test_194c_single_below_and_aggregate_below(self):
        r = run("T16", invoice_patch={"lines": [{"description": "x", "taxable_value": 20000, "gst": 0}]})
        self.assertEqual(int(r.tds_total), 0)  # 28k + 29k + 20k = 77k, each < 30k

    def test_transporter_without_pan_loses_exemption(self):
        r = run("T09", vendor_patch={"pan": None, "pan_operative": False})
        self.assertEqual(int(r.tds_total), 17000)  # 20% under 206AA

    def test_no_pan_flag(self):
        self.assertIn("no_pan_206AA", run("T10").flags)
        self.assertIn("no_pan_206AA", run("T21").flags)

    def test_rent_exactly_at_limit_not_taxable(self):
        r = run("T14", invoice_patch={"lines": [{"description": "x", "taxable_value": 600000, "gst": 0}]})
        self.assertEqual(int(r.tds_total), 0)  # 50,000/month is not *more than* 50,000

    def test_non_tax_codes_skip_engine(self):
        r = run("T11", codes=["NO_TDS", "UNSURE"])
        self.assertEqual(r.sections, [])


if __name__ == "__main__":
    unittest.main()
