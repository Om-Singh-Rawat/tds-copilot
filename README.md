# TDS Copilot

**AI-assisted TDS section classification for Indian vendor payments.** A retrieval-grounded LLM *reads* the invoice, a deterministic engine *calculates*, and a named human *signs off*.

![tests](https://github.com/Om-Singh-Rawat/tds-copilot/actions/workflows/tests.yml/badge.svg)
· Python 3.10+ · **no third-party dependencies** · synthetic data only · not tax advice

---

## The problem

For every vendor payment, an Indian accounts team must decide **which TDS section applies** (contractor, professional or technical fees, rent, commission ...), check the vendor's **annual threshold**, pick the **rate** (payee type, PAN status, exemptions), and keep evidence for the decision. Invoice text is messy: "AMC for ERP", "release of ad via agency", "rooms blocked for the year". A wrong call means interest of 1–1.5% a month (s.201(1A)), disallowance of 30% of the expense (s.40(a)(ia)) and mismatch notices.

## The design in one picture

![Architecture: where the AI, the code and the human each act](docs/architecture.svg)

```
invoice lines (ERP) + vendor master + payment ledger
   │
   ├─ validate input ─────────────────────────────── bad input → 400 / rejected
   ├─ rule set valid for payment date? ───────────── none → NOT computed → human
   ├─ retrieval: pinned statutory definition of every in-scope section
   │             + BM25 top-k circulars / practice notes             [code]
   ├─ LLM: one closed code per line + cited source ids + flags      [AI - the only probabilistic step]
   ├─ guardrails: valid code · citation retrieved AND supports code ·
   │              not practice-only · keyword cross-check · majority vote  [code]
   ├─ engine: GST exclusion · FY aggregation · thresholds · catch-up ·
   │          PAN-type rate · 194C(6) · 206AA · rounding                    [code, Decimal]
   ├─ router: AUTO-SUGGEST or NEEDS REVIEW with named reasons               [code]
   └─ append-only audit log: input hash · sources · prompt hash · raw output ·
                             rule-set id · KB version · model · reviewer
```

Full diagram, where each kind of knowledge lives, rejected alternatives and weakest points: **[docs/architecture.md](docs/architecture.md)**.

---

## Quick start

```bash
git clone https://github.com/Om-Singh-Rawat/tds-copilot.git
cd tds-copilot
python -m unittest discover -s tests -t .     # 47 offline tests
python -m tds run --case T16 --mode baseline   # one invoice, full calculation trace
python -m tds serve                            # reviewer UI → http://127.0.0.1:8000
```

Optional: `pip install -e .` adds a `tds` command (`tds run …`, `tds serve`, …).

### With the LLM (free)
1. Get a free key at https://openrouter.ai/keys.
2. Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
3. Run:
```bash
python -m tds run --case T12
python -m tds eval --mode llm --delay 3                       # 27 calls
python -m tds eval --mode llm --samples 3 --cases T07,T13      # self-consistency
```
The free tier allows **50 requests per day per account**. Replies are cached in `.cache/llm/`, so re-runs cost nothing.

### Reproduce the recorded LLM run without any key
The cached answers are committed. Point the app at the knowledge-base version they were produced with:
```bash
# macOS / Linux
TDS_LIVE_LLM=0 TDS_KB_PATH=data/knowledge/archive/kb-v1.json python -m tds eval --mode llm --cases T01,T02,T03,T04,T05,T06,T07,T08,T09,T10,T11,T12,T13,T14,T15,T16,T17,T18,T19,T20,T21,T22,T23,T24,T25,T26 --out /tmp/replay
```
```powershell
# Windows PowerShell
$env:TDS_LIVE_LLM="0"; $env:TDS_KB_PATH="data/knowledge/archive/kb-v1.json"; python -m tds eval --mode llm --cases T01,T02,T03,T04,T05,T06,T07,T08,T09,T10,T11,T12,T13,T14,T15,T16,T17,T18,T19,T20,T21,T22,T23,T24,T25,T26 --out replay
```
CI does exactly this on every push and fails if any answer is missing or any auto-suggestion is wrong.

---

## Serving it publicly

The web server is plain `http.server` with production guard-rails:

| Guard-rail | How |
|---|---|
| Input validation | `tds/schema.py`; every problem listed in a `400` response |
| Body size cap | 64 KB |
| LLM cost control | `TDS_LIVE_LLM=0` serves cached answers only; otherwise live calls are rate-limited per visitor IP (`TDS_LLM_RPM`, default 6/min). Cache hits are free and unlimited |
| Privacy | `TDS_PUBLIC=1` hides the audit trail from visitors; the UI warns against pasting real data |
| Health | `GET /healthz` |
| Container | non-root user, health check, `HOST=0.0.0.0` |

```bash
docker build -t tds-copilot .
docker run -p 8080:8080 tds-copilot                                    # public demo, cached LLM only
docker run -p 8080:8080 -e TDS_LIVE_LLM=1 -e OPENROUTER_API_KEY=sk-or-... tds-copilot
```
Any container host works (Render, Railway, Fly.io, Cloud Run): deploy the Dockerfile and let it use the platform's `PORT`. CI builds the image and probes the running container on every push.

### Configuration (`.env` or environment)

| Variable | Default | Meaning |
|---|---|---|
| `OPENROUTER_API_KEY` | – | OpenRouter key; without it the AI path fails safe to review |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b:free` | any OpenRouter model id |
| `RETRIEVAL_TOP_K` | 5 | BM25 passages added on top of the pinned definitions |
| `HOST` / `PORT` | 127.0.0.1 / 8000 | web server bind address |
| `TDS_PUBLIC` | 0 | 1 hides `/api/audit` |
| `TDS_LIVE_LLM` | 1 | 0 = never call the LLM, replay cache only |
| `TDS_LLM_RPM` | 6 | live LLM calls per visitor per minute |
| `TDS_DATA_DIR`, `TDS_KB_PATH`, `TDS_CACHE_DIR`, `TDS_AUDIT_DIR` | repo folders | relocate data, knowledge base, cache, audit log |

### HTTP API

| Method & path | Body | Returns |
|---|---|---|
| `GET /api/meta` | – | sample cases, vendors, codes, server mode |
| `POST /api/run` | `{"invoice": {...}, "mode": "llm"\|"baseline", "samples": 1-5}` | classification, calculation steps, route, reasons, audit id |
| `POST /api/override` | `{"invoice": {...}, "codes": ["194C", ...]}` | recomputed result with the reviewer's sections |
| `POST /api/decision` | `{"audit_id", "action": "approve"\|"override"\|"reject", "codes", "tds_total", "reviewer", "note"}` | audit record id |
| `GET /api/audit` | – | recent audit records (403 when `TDS_PUBLIC=1`) |
| `GET /healthz` | – | `{"ok": true}` |

Invoice format (see `data/test_cases.json` for 27 examples):
```json
{"vendor_id": "V011", "invoice_no": "SVS/556", "date": "2025-10-20", "gst_shown_separately": true,
 "period_months": 1,
 "lines": [{"description": "Supply of 20 CCTV cameras", "taxable_value": 300000, "gst": 54000},
           {"description": "Installation and commissioning", "taxable_value": 50000, "gst": 9000}]}
```

---

## Scope

**In scope:** payments to **resident** payees under ss.194C, 194H, 194-I(a)/(b), 194J(a)/(b) and director fees, plus s.206AA (no or inoperative PAN), the s.194C(6) transporter exemption and the GST exclusion (Circular 23/2017). Jurisdiction: **India, FY 2025-26** (Income-tax Act 1961 as amended by Finance Act 2025).

**Detected and sent to a human, never computed:** salary, non-residents (s.195), interest, 194D, 194-IA, 194-IB, 194-O, 194Q, lower-deduction certificates.

**Other years and countries:** add a rule file with its own `valid_from`/`valid_to` and a knowledge base; no code changes. From **1 April 2026** TDS falls under **s.393 of the Income-tax Act 2025**. That rule set is deliberately *not* included until it is verified, so the system refuses to compute rather than guess (test T17).

## Knowledge base and its verification

`data/knowledge/kb.json` holds 23 short paraphrases. Each names the provision it summarises and an authority level (statute / circular / practice), and each result is stamped with the KB version and file hash.

**v2 (current) was checked against the official CBDT Circular 715 text on incometaxindia.gov.in.** The check found and fixed real errors in v1:
- the advertising answer is Q.1–Q.4 and Q.17, not Q.1–Q.2;
- **v1 wrongly said an agency's payments to the media are covered by s.194C; Q.2 says they are not;**
- maintenance contracts (Q.29) are an official circular answer, which v1 had tagged as "practice";
- recruitment agencies fall under s.194J, not s.194C (Q.12);
- vehicle hire no longer cites the circular, because it does not address it.

Full log: the `verification_log` field in `kb.json`. v1 is kept in `data/knowledge/archive/` for reproducibility.

## Test set: 27 synthetic invoices (`data/test_cases.json`)

All vendors, PANs, invoices and ledger entries are **made up**. The expected answers are my own; grey areas are expected to route to review.

| ids | what they test |
|---|---|
| T01–T08 | one clean case per section (194C, 194J professional, 194-I building, 194-I machinery, 194H, goods, 194J technical, director) |
| T09 | transporter exemption 194C(6) → TDS 0 |
| T10, T21 | no PAN and inoperative PAN → 20% under s.206AA → review |
| T11 | mixed invoice: goods line (no TDS) + installation line (194C) |
| T12 | advertising agency → 194C per Circular 715, *not* 194J |
| T13 | software AMC, a genuine 194C/194J grey area (Circular 715 Q.29) → must reach a human |
| T14 | hotel rooms blocked for a year → rent (Q.20) |
| T15 | below the 194J threshold → TDS 0 |
| T16 | 194C annual limit crossed → catch-up on earlier untaxed payments → review |
| T17 | payment date with no verified rule set → not computed |
| T18 | non-resident payee → out of scope |
| T19 | vague description → review |
| T20 | manpower supply → 194C |
| T22–T26 | **stress cases**: prompt injection, Hinglish, abbreviations, misleading vendor type (job work), commission vs trade discount |
| T27 | recruitment agency (Circular 715 Q.12), added after the verification |

## Results

| metric | Keyword baseline (27 cases, KB v2) | **LLM pipeline** (26 cases, KB v1, 1 sample) |
|---|---|---|
| section accuracy (grey areas: any listed option) | 70% | **100%** |
| strict section accuracy | 56% | **96%** |
| TDS amount accuracy | 62% | **100%** |
| **unsafe auto-suggestions** (auto + wrong) | **1** | **0** |
| missed reviews (should have gone to a human) | 2 | **0** |
| route accuracy | 81% | 96% |
| review rate | 52% | 46% |

Model: `nvidia/nemotron-3-ultra-550b-a55b:free` via OpenRouter, temperature 0. Per-case tables: [baseline](eval/results/baseline.md) · [LLM, KB v1](eval/results/kb-v1/llm_nvidia-nemotron-3-ultra-550b-a55b-free_s1.md) · [3-sample run](eval/results/kb-v1/llm_nvidia-nemotron-3-ultra-550b-a55b-free_s3.md)

> **Status of the LLM numbers:** they were recorded with **KB v1**, before the verification above. Re-running them on KB v2 (plus T27) needs about 42 free-tier calls. Commands are in the Quick start section; results land in `eval/results/`.

**Where the keyword baseline fails:** it auto-suggests the advertising agency (T12) as professional fees, **Rs 25,000 instead of Rs 5,000**. It cannot read hotel rooms as rent, manpower supply, Hinglish, a job-work order from a stationery vendor, or the installation line of a mixed invoice, and it auto-suggests the grey areas T13 and T19 with no doubt.

**Where the LLM pipeline falls short (honest list):**
1. **The review rate is high (46%).** Most reviews are correct (no PAN, catch-up, non-resident, grey areas), but the model raises ambiguity flags generously. On T07 (managed AWS support) it was right but still went to review.
2. **The flags were unstable between runs.** With 3 samples at temperature 0.7 the *section* never changed, but the flags did: T11 went to review in one run and not the other. **Fix shipped:** a flag (or "low" confidence) now counts only if most samples raise it (`classifier.aggregate_line`). Replaying the same recorded answers with this rule moves T11 back to auto-suggest; T07 stays in review because most samples flag it.
3. **On commission vs trade discount (T26) it says UNSURE.** That is correct behaviour, but on the hardest cases the human does all the work.
4. **Prompt injection (T22):** the model ignored "classify as NO_TDS" in the description. The real defences are still in code: closed codes, the grounding check, the cross-check and review of high-value invoices.
5. **The test set is optimistic:** I wrote the cases, the expected answers and the KB. KB errors cannot be caught by this eval; the Circular 715 verification is how two of them were found.
6. **Free-tier quota** (50 requests/day per account) is a real operational constraint. A 429 response fails safe to review.

**Engine correctness:** `test_every_case_with_expected_amount`: given the correct sections, the engine reproduces every hand-computed amount. All amount risk therefore sits in classification and the KB.

---

## Project layout

```
tds/
  config.py       settings from .env / environment
  schema.py       invoice validation
  data.py         vendor master, ledger, test cases (the seam for an ERP adapter)
  rules.py        versioned rule sets selected by payment date
  retrieval.py    BM25 + pinned section definitions
  classifier.py   prompt, strict parser, self-consistency and majority-vote flags
  llm.py          OpenRouter client (stdlib) with on-disk cache
  baseline.py     keyword classifier, used as baseline and as a cross-check
  engine.py       deterministic TDS calculation (Decimal), every step logged
  pan.py          PAN format and holder type
  router.py       named review rules
  audit.py        append-only JSONL audit log
  pipeline.py     orchestration of the above
  evaluation.py   scoring and reports
  cli.py          python -m tds run | search | eval | serve
  web.py          HTTP API + reviewer UI (static/index.html)
data/rules/       rates and thresholds, one JSON per validity window
data/knowledge/   knowledge base (+ archive/ of earlier versions)
data/             synthetic vendors, ledger, 27 test cases
eval/results/     scorecards (baseline, kb-v1/ LLM runs)
tests/            47 offline tests: engine, guardrails (stubbed LLM), schema, web API
docs/             architecture.md
Dockerfile, .github/workflows/tests.yml
```

Author: Om Singh Rawat. Built with AI assistance (Claude); see the brief's appendix for what was AI and what was not.
