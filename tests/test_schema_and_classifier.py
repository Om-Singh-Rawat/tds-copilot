import copy
import unittest

from tds import data
from tds.classifier import aggregate_line, parse
from tds.schema import InvalidInvoice, validate_invoice

GOOD = data.test_case("T11")["invoice"]


def bad(**patch):
    inv = copy.deepcopy(GOOD)
    inv.update(patch)
    return inv


class SchemaTests(unittest.TestCase):
    def test_valid_invoice_normalised(self):
        inv = validate_invoice(GOOD)
        self.assertEqual(inv["period_months"], 1)
        self.assertEqual(len(inv["lines"]), 2)

    def test_rejects_and_lists_every_problem(self):
        with self.assertRaises(InvalidInvoice) as ctx:
            validate_invoice(bad(date="31-12-2025", vendor_id="", lines=[{"description": "", "taxable_value": -5}]))
        errs = " | ".join(ctx.exception.errors)
        for fragment in ("vendor_id", "date", "description", "taxable_value"):
            self.assertIn(fragment, errs)

    def test_rejects_non_numeric_and_bool_amounts(self):
        for value in ("1000", True, None):
            with self.subTest(value=value), self.assertRaises(InvalidInvoice):
                validate_invoice(bad(lines=[{"description": "x", "taxable_value": value}]))

    def test_rejects_oversized_description(self):
        with self.assertRaises(InvalidInvoice):
            validate_invoice(bad(lines=[{"description": "x" * 501, "taxable_value": 1}]))

    def test_rejects_non_object(self):
        with self.assertRaises(InvalidInvoice):
            validate_invoice(["not", "an", "invoice"])


def sample(code, flags=(), conf="high", cites=("kb-194C-scope",)):
    return {"line": 1, "code": code, "citations": list(cites), "confidence": conf,
            "ambiguity_flags": list(flags), "reasoning": "", "nature_of_payment": ""}


class AggregationTests(unittest.TestCase):
    def test_single_sample_keeps_flags(self):
        out = aggregate_line([sample("194C", ["grey_area"], "low")], "194C")
        self.assertEqual(out["ambiguity_flags"], ["grey_area"])
        self.assertEqual(out["confidence"], "low")

    def test_minority_flag_dropped(self):
        s = [sample("194C", ["grey_area"]), sample("194C"), sample("194C")]
        self.assertEqual(aggregate_line(s, "194C")["ambiguity_flags"], [])

    def test_majority_flag_kept_and_free_text_grouped(self):
        s = [sample("194C", ["other: a"]), sample("194C", ["other: b"]), sample("194C")]
        self.assertEqual(aggregate_line(s, "194C")["ambiguity_flags"], ["other"])

    def test_minority_low_confidence_not_low(self):
        s = [sample("194C", conf="low"), sample("194C"), sample("194C")]
        self.assertNotEqual(aggregate_line(s, "194C")["confidence"], "low")

    def test_citations_merged_from_agreeing_samples_only(self):
        s = [sample("194C", cites=["a"]), sample("194C", cites=["b"]), sample("194J_A", cites=["c"])]
        self.assertEqual(aggregate_line(s, "194C")["citations"], ["a", "b"])


class ParseTests(unittest.TestCase):
    def test_parses_json_wrapped_in_prose(self):
        txt = 'Here you go:\n```json\n{"lines":[{"line":1,"code":"194c","citations":["kb-194C-scope"]}]}\n```'
        self.assertEqual(parse(txt, 1)[0]["code"], "194C")

    def test_missing_line_rejected(self):
        with self.assertRaises(ValueError):
            parse('{"lines":[{"line":1,"code":"194C"}]}', 2)


if __name__ == "__main__":
    unittest.main()
