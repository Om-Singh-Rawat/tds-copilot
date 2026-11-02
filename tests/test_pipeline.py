"""Pipeline and router tests with a stubbed LLM, so they run offline and prove
that the guardrails catch bad model output."""
import json
import unittest

from tds import config, data
from tds.pipeline import process

CASES = {c["id"]: c["invoice"] for c in data.test_cases()}


def stub(lines: list[dict] | str, model: str = "stub-model"):
    """Fake chat_fn returning a fixed reply (or one reply per sample if a list of lists)."""
    def chat_fn(messages, model=None, temperature=0.0, sample_idx=0):
        payload = lines if isinstance(lines, str) else json.dumps({"lines": lines[sample_idx] if isinstance(lines[0], list) else lines})
        return {"content": payload, "model": "stub-model"}
    return chat_fn


def line(code, cites, conf="high", flags=(), n=1):
    return {"line": n, "code": code, "citations": list(cites), "confidence": conf,
            "ambiguity_flags": list(flags), "reasoning": "stub"}


def reasons(r):
    return {x["code"] for x in r["reasons"]}


class PipelineTests(unittest.TestCase):
    def go(self, case, chat_fn, **kw):
        return process(CASES[case], mode="llm", chat_fn=chat_fn, write_audit=False, **kw)

    def test_grounded_answer_auto(self):
        r = self.go("T01", stub([line("194C", ["kb-194C-scope", "kb-circ715-labour"])]))
        self.assertEqual(r["route"], "auto", r["reasons"])
        self.assertEqual(r["tds_total"], 2400)

    def test_citation_not_retrieved_goes_to_review(self):
        r = self.go("T01", stub([line("194C", ["kb-made-up"])]))
        self.assertEqual(r["route"], "review")
        self.assertIn("ungrounded_citation", reasons(r))

    def test_citation_that_does_not_support_code(self):
        # cites a real, retrieved chunk - but one about rent, while claiming 194C
        r = self.go("T01", stub([line("194C", ["kb-194I"])]))
        self.assertIn("ungrounded_citation", reasons(r))

    def test_garbage_output_goes_to_review(self):
        r = self.go("T01", stub("Sure! The answer is 194C."))
        self.assertEqual(r["route"], "review")
        self.assertIn("classifier_error", reasons(r))
        self.assertIsNone(r["tds_total"], "undecided must not be reported as zero TDS")

    def test_invalid_code_rejected(self):
        r = self.go("T01", stub([line("194Z", ["kb-194C-scope"])]))
        self.assertIn("classifier_error", reasons(r))

    def test_unsure_goes_to_review(self):
        r = self.go("T13", stub([line("UNSURE", [], conf="low")]))
        self.assertIn("unsure", reasons(r))

    def test_practice_only_goes_to_review(self):
        r = self.go("T04", stub([line("194I_A", ["kb-equipment-hire"])]))
        self.assertIn("practice_only", reasons(r))

    def test_baseline_disagreement(self):
        # keyword baseline matches 194J_B ('advertis'); model says 194C
        r = self.go("T12", stub([line("194C", ["kb-circ715-advertising"])]))
        self.assertIn("baseline_disagrees", reasons(r))
        self.assertEqual(r["tds_total"], 5000)

    def test_split_vote_with_samples(self):
        votes = [[line("194J_A", ["kb-194J-fts"])], [line("194C", ["kb-194C-scope"])], [line("194J_A", ["kb-194J-fts"])]]
        r = self.go("T07", stub(votes), samples=3)
        self.assertEqual(r["classifications"][0]["code"], "194J_A")
        self.assertIn("split_vote", reasons(r))

    def test_no_rule_set_for_date(self):
        r = self.go("T17", stub([line("194C", ["kb-194C-scope"])]))
        self.assertIsNone(r["tds_total"])
        self.assertIn("no_rule_set", reasons(r))

    def test_non_resident_never_computed(self):
        r = self.go("T18", stub([line("194J_B", ["kb-194J-prof"])]))
        self.assertIsNone(r["tds_total"])
        self.assertIn("non_resident", reasons(r))

    def test_mixed_invoice_per_line(self):
        r = self.go("T11", stub([line("NO_TDS", ["kb-goods"], n=1), line("194C", ["kb-194C-scope"], n=2)]))
        self.assertEqual(r["tds_total"], 1000)

    def test_human_override_recomputes(self):
        r = process(CASES["T13"], mode="human", override_codes=["194C"], write_audit=False)
        self.assertEqual(r["route"], "human_decided")
        self.assertEqual(r["tds_total"], 2400)

    def test_no_api_key_fails_safe(self):
        saved, config.OPENROUTER_API_KEY = config.OPENROUTER_API_KEY, ""
        try:
            r = process(CASES["T02"], mode="llm", write_audit=False)
        finally:
            config.OPENROUTER_API_KEY = saved
        # either served from cache (if a run already happened) or failed safe to review
        if r["error"]:
            self.assertEqual(r["route"], "review")


if __name__ == "__main__":
    unittest.main()
