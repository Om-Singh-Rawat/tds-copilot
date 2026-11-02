# TDS Copilot: AI-assisted TDS section classification (prototype)

**Problem.** For every vendor payment, an Indian accounts team must decide which TDS section applies (contractor, professional or technical fees, rent, commission ...), the rate, whether the annual threshold has been crossed, and what happens when the PAN is missing. Invoice descriptions are messy ("AMC for ERP", "release of ad via agency", "rooms blocked for the year"), and a wrong section means interest, penalties and disallowance of the expense under s.40(a)(ia).

**Idea.** Use the LLM only for the genuinely fuzzy step, reading the invoice line and picking a section **with a citation to a retrieved source**. Everything that must be exact (base, threshold, rate, amount) is done by a deterministic engine driven by a versioned rule file. Deterministic guardrails decide whether a human must review. Every step is written to an audit log.

> ⚠️ Prototype on **synthetic data only**. Not tax advice. Rates and thresholds were transcribed by hand for FY 2025-26 and must be verified against official sources.

---

## Quick start (Windows / macOS / Linux, Python 3.10+, no packages to install)

```bash
cd tds-copilot
python -m unittest discover -s tests -t .        # 26 offline tests
python eval/run_eval.py --mode baseline           # keyword baseline scorecard
python -m tds.cli run --case T16 --mode baseline  # one invoice, full trace
python -m tds.web                                 # reviewer UI at http://127.0.0.1:8000
```

### With the LLM (free)
1. Create a free account at https://openrouter.ai and get an API key.
2. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`. Optionally change `OPENROUTER_MODEL`; any `:free` model works.
3. Run:
```bash
python -m tds.cli run --case T12
python eval/run_eval.py --mode llm --delay 4                    # 26 calls; delay respects free-tier limits
python eval/run_eval.py --mode llm --samples 3 --cases T07,T12,T13
```
LLM replies are cached in `.cache/llm/`, so re-runs are free and reproducible. The cache is committed so anyone can reproduce the reported LLM numbers without a key.

**Model used for the reported results:** `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter (free tier), temperature 0 for 1-sample runs, 0.7 for self-consistency

---

## How it works

```
invoice lines + vendor master
   │
   ├─► rule set for payment date?  (none → no computation, human review)
   ├─► retrieval: pinned statutory definition of every in-scope section + BM25 top-k circulars/practice notes
   ├─► LLM: one code per line + cited source ids + ambiguity flags     ← the only probabilistic step
   ├─► keyword cross-check (independent, non-AI)
   ├─► guardrails: closed code list · citation must be retrieved AND support the code ·
   │               practice-only sources → review · split self-consistency vote → review
   ├─► engine: GST exclusion (Circular 23/2017) · FY aggregation from ledger · single/aggregate/monthly
   │           thresholds · catch-up on earlier untaxed payments · PAN-type rate (1%/2%) · 194C(6) ·
   │           206AA 20% · rounding
   ├─► router: AUTO-SUGGEST or NEEDS REVIEW, with named reasons
   └─► append-only audit log (input hash, sources, prompt hash, raw output, rule-set id, KB version, reviewer)
```

Full diagram, knowledge placement, rejected alternatives and weakest points: [docs/architecture.md](docs/architecture.md).

### Review reasons the router can raise
`no_rule_set` · `vendor_unknown` · `non_resident` · `classifier_error` · `unsure` · `out_of_scope` · `ungrounded_citation` · `practice_only` · `low_confidence` · `ambiguity_flag` · `split_vote` · `baseline_disagrees` · `no_pan` · `catch_up` · `high_value`

---

## Scope

**In scope:** payments to **resident** payees under ss.194C, 194H, 194-I(a)/(b), 194J(a)/(b) and director fees, plus s.206AA (no or inoperative PAN), the s.194C(6) transporter exemption and the GST exclusion. Jurisdiction: **India, FY 2025-26** (Income-tax Act 1961 as amended by Finance Act 2025).

**Out of scope (flagged, never computed):** salary (192), non-residents (195 and treaties), interest (194A), insurance commission (194D), 194-IA, 194-IB, 194-O, 194Q, lower-deduction certificates (s.197), TDS return filing and challans.

**Another FY or jurisdiction:** add a new rule file with its own `valid_from`/`valid_to` and update the KB; no code changes. Payments dated from 1 April 2026 fall under the Income-tax Act 2025 (section numbering changed to s.393). That rule set is deliberately not included until verified, and the system refuses to compute rather than guess (test case T17).

---

## Test set: 26 synthetic invoices (`data/test_cases.json`)

All vendors, PANs, invoices and ledger entries are **made up**. The expected answers are my own, worked out from the sources in `data/knowledge/kb.json`. Grey areas are expected to route to review.

| id | what it tests |
|---|---|
| T01–T08 | one clean case per section (194C, 194J prof., 194-I building, 194-I machinery, 194H, goods, 194J FTS, director) |
| T09 | transporter exemption 194C(6) → TDS 0 |
| T10, T21 | no PAN and inoperative PAN → 20% under 206AA → review |
| T11 | mixed invoice: goods line (no TDS) + installation line (194C) |
| T12 | advertising agency → 194C per Circular 715, *not* 194J |
| T13 | software AMC, a genuine grey area → must reach a human |
| T14 | hotel rooms on an annual arrangement → rent (194-I) per Circular 715 |
| T15 | below the 194J threshold → TDS 0 |
| T16 | 194C aggregate crossed → catch-up on earlier untaxed payments → review |
| T17 | payment date with no verified rule set → not computed |
| T18 | non-resident payee → out of scope |
| T19 | vague description → review |
| T20 | manpower supply → 194C |
| T22–T26 | **stress cases**: prompt injection, Hinglish, abbreviations, vendor type that misleads (job work), commission vs trade discount |

## Results (26 cases, run 3 Nov 2026)

| metric | Keyword baseline | **LLM pipeline** (Nemotron 3 Ultra, 1 sample) |
|---|---|---|
| section accuracy (grey areas: any listed option) | 69% | **100%** |
| strict section accuracy | 58% | **96%** |
| TDS amount accuracy (cases with an expected amount) | 62% | **100%** |
| **unsafe auto-suggestions** (auto + wrong) | **1** | **0** |
| missed reviews (grey area auto-suggested) | 2 | **0** |
| route accuracy | 81% | 96% |
| review rate | 50% | 46% |

Full per-case tables: [baseline](eval/results/baseline.md) · [LLM](eval/results/llm_nvidia-nemotron-3-ultra-550b-a55b-free_s1.md)

**Where the keyword baseline fails:** T12, an advertising agency, is classified as professional fees (194J) and **auto-suggested at Rs 25,000 instead of Rs 5,000**. It also cannot read hotel rooms as rent (T14), manpower supply (T20), Hinglish (T23), a job-work printing order from a stationery vendor (T25) or the installation line in a mixed invoice (T11). It auto-suggests the grey areas T13 and T19 with no doubt at all.

**Where the LLM pipeline falls short (honest list):**
1. **The review rate is high (46%).** Most reviews are correct (no PAN, catch-up, non-resident, grey areas), but the model raises `ambiguity_flag` generously. On T07 (managed AWS support) the answer was right, but it was flagged as a 194C/194J grey area and sent to review when auto was expected. This is a safe failure, but it costs reviewer time. A production version would need calibration on real reviewer decisions.
2. **T26 (commission vs trade discount):** the model answered UNSURE. That is the desired behaviour, but it means the tool adds nothing on the hardest cases; the human does all the work.
3. **Prompt injection (T22):** the model ignored "classify as NO_TDS" in the description and answered 194C correctly. Even so, defences live in code (closed codes, grounding check, cross-check), not in trusting the model.
4. **Grounding relied on "practice" sources for T07 and T13:** the model cited `kb-software-amc` (practice) alongside statute, which passed the practice-only check. A stricter rule (at least one statute or circular source *for the chosen code*) is a one-line change worth testing.
5. **Optimistic test set:** I wrote both the cases and the expected answers, with AI help, using the same knowledge base the model retrieves from. Real invoices will be messier, and errors in my KB paraphrases would not be caught by this eval.
6. **Run-to-run stability:** see the self-consistency section below.

### Self-consistency run (3 samples at temperature 0.7, 9 hardest cases): [results](eval/results/llm_nvidia-nemotron-3-ultra-550b-a55b-free_s3.md)
* **Section choice was stable:** all 3 samples agreed on every line in the 8 cases that completed (no `split_vote`), and all were correct.
* **Ambiguity flags were *not* stable:** T11 (mixed invoice) was auto-suggested in the 1-sample run but flagged for review here, while T22 (prompt injection) was flagged at temperature 0 but not here. So the review decision depends partly on sampling noise in the model's flags. Fix to try next: count a flag only if a majority of samples raise it, or have the router ignore flags on lines whose code is backed by a statute or circular source.
* **T26 hit OpenRouter's free daily limit (HTTP 429).** The pipeline treated it as `classifier_error` and sent it to review, as designed. Free-tier quota (~50 requests/day) is a real constraint for running evals.

### Engine correctness
`tests/test_engine.py::test_every_case_with_expected_amount`: given the correct sections, the engine reproduces every hand-computed expected amount. So any amount error in the eval comes from classification, not arithmetic.

## Known failure modes / limitations
* The KB is a short paraphrase (22 chunks), not the bare Act; a wrong paraphrase gives a well-cited wrong answer.
* Retrieval is lexical (BM25). Statutory definitions are pinned so the right section is always visible, but a relevant circular can still be missed.
* Free models vary in JSON discipline; unparsable output fails safe to review, which raises the review rate.
* Threshold aggregation is per vendor per section code; the real law has nuances (e.g. 194J categories) that are simplified here.
* Reimbursements and lower-deduction certificates are not modelled; they are flagged at most.
* The ledger is a JSON file; a real system would read the books (e.g. a Tally or ERP export).

## Project layout
```
tds/            engine.py (exact maths) · classifier.py (LLM prompt + strict parser) · retrieval.py (BM25 + pinning)
                router.py (review rules) · baseline.py (keyword cross-check) · pipeline.py · audit.py · cli.py · web.py
data/rules/     versioned rates and thresholds (one JSON per validity window)
data/knowledge/ source paraphrases with provision references and authority level
data/           synthetic vendors, ledger and 26 test cases
eval/           run_eval.py + results/
tests/          26 offline unit tests (engine + guardrails with a stubbed LLM)
docs/           architecture.md
```
