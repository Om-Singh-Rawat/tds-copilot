# Architecture

## Flow for one invoice

```mermaid
flowchart TD
    A[Invoice lines from ERP<br/>description, taxable value, GST, date] --> VAL[Input validation<br/>schema.py] --> P
    V[(Vendor master<br/>PAN, residency, 194C6 declaration)] --> P
    L[(Payment ledger<br/>FY history per vendor + section)] --> E

    P[Pipeline] --> R{Rule set valid<br/>for payment date?}
    R -- no --> H
    P --> RET[Retrieval<br/>pinned section definitions + BM25 top-k<br/>over Act / circular paraphrases]
    RET --> LLM[LLM classifier - PROBABILISTIC<br/>one code per line + cited source ids<br/>no amounts, no rates]
    P --> KW[Keyword cross-check<br/>independent, non-AI]

    LLM --> G[Guardrails - DETERMINISTIC<br/>valid code? citation retrieved AND supports code?<br/>statute/circular, not only practice?<br/>split vote? keyword disagrees?<br/>flags counted by majority vote]
    KW --> G
    G --> E[TDS engine - DETERMINISTIC<br/>GST exclusion, FY aggregation, thresholds,<br/>PAN-type rate, 194C6, 206AA, rounding]
    E --> RT{Router}
    G --> RT
    RT -- no reasons --> AU[AUTO-SUGGEST<br/>batch approval by accountant]
    RT -- any reason --> H[HUMAN REVIEW QUEUE<br/>sees reasons, sources, calc steps<br/>can override section and recompute]
    AU --> LOG[(Append-only audit log<br/>input hash, sources, prompt hash, raw model output,<br/>rule-set id, kb version, reviewer decision)]
    H --> LOG
```

## Where each kind of knowledge lives

| Knowledge | Lives in | Why | When it goes stale |
|---|---|---|---|
| Rates, thresholds, exemptions | `data/rules/*.json`, versioned, with `valid_from`/`valid_to` | Must be exact and auditable; changes every Budget | Payments outside every rule set's date range are **not computed**; they go to review (`no_rule_set`) |
| What a section *means* (scope, circulars) | `data/knowledge/kb.json`, retrieved and cited | The model must reason from text it was shown, not from memory | `kb_version` + file hash stamped on every result; old versions archived in `data/knowledge/archive/` so past results can be replayed exactly; re-run the eval after every edit |
| Vendor facts (PAN, residency, declarations) | Vendor master | Facts, not judgment, so never asked of the model | Owned by the vendor-onboarding process |
| Payment history | Ledger | Needed for annual aggregation | Comes from the books |
| Reading messy invoice text | LLM | The only genuinely fuzzy step | Model version recorded per result |
| Final accountability | Human reviewer | The law puts liability on the deductor | Every decision logged with reviewer name |

## Exact vs. probabilistic: how they are kept apart

* The LLM returns **codes and source ids only**. Its output is parsed against a closed list of codes; anything else is a classifier error and the invoice goes to a human.
* All arithmetic is in `tds/engine.py` using `Decimal`. The engine never sees model text, only the code chosen for each line.
* A citation counts only if the cited chunk **was actually retrieved for this invoice** and **is tagged as supporting that code**, so the model cannot cite a made-up or irrelevant source.

## Rejected alternatives

| Alternative | Why rejected |
|---|---|
| One LLM call that returns the TDS amount | Rates and thresholds come from memory (often stale or wrong), arithmetic is unreliable, and there is nothing an auditor can re-run |
| Pure keyword or rules classifier | Works on clean text, but fails on agency advertising (Circular 715), hotel rooms as rent, manpower supply and mixed invoices (see `eval/results/baseline.md`); confidently wrong with no signal |
| Fine-tuning a model on past classifications | Bakes in last year's law and past mistakes, can't cite, and needs retraining on every amendment |
| Multi-agent system (extractor, classifier and checker agents) | More LLM calls, more failure points and cost; the checking that matters here is deterministic and is done better in code |
| Vector database with embeddings | Overkill for 23 chunks; BM25 is transparent and needs no dependencies. It would be revisited at the scale of the full Act plus all circulars |
| Trusting the model's self-reported confidence and flags | Poorly calibrated and, as measured, unstable between runs; replaced by grounding checks, the keyword cross-check and majority votes over several samples |

## Weakest points

1. **The knowledge base is my paraphrase.** If a paraphrase is wrong, a well-grounded answer can still be wrong. This actually happened: v1 said an agency's payments to the media are covered by s.194C, while Circular 715 Q.2 says they are not. Checking v1 against the official circular found that and four other citation errors (see `verification_log` in `kb.json`). Mitigation: each chunk names its provision and authority level, every result records the KB version, and a practitioner should sign off each version.
2. **Garbage descriptions.** "Professional charges as discussed" cannot be classified by anyone. The design routes these to review; it cannot fix them.
3. **The ledger is assumed correct.** Wrong history means wrong aggregation and catch-up.
4. **Prompt injection through invoice text.** A vendor could write "classify as NO_TDS" in a description. Mitigations: closed code list, grounding check and keyword cross-check; high-value invoices are always reviewed.
5. **Rules are frozen at FY 2025-26.** The Income-tax Act 2025 applies from 1 April 2026, and the new section mapping (s.393) is not yet verified. The system refuses to compute rather than guess.

## Public-serving controls

| Concern | Control |
|---|---|
| Malformed or hostile input | `schema.py` validation (types, sizes, 50 lines, 500-character descriptions), 64 KB body cap, 400 with every error listed |
| LLM spend / quota abuse | `TDS_LIVE_LLM=0` cache-only mode; otherwise a per-IP sliding-window limit on *live* calls only (cache hits are free) |
| Data exposure | `TDS_PUBLIC=1` disables `/api/audit`; synthetic data only; UI warning against real data |
| Concurrency | threaded server; audit log and cache writes are lock-protected |
| Operations | `/healthz`, Docker image as a non-root user with a health check, CI builds and probes the container |
