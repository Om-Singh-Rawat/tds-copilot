"""Scoring of pipeline results against the synthetic test set.

Metrics
  section_acc    every line's code is acceptable (expected, or in accept_sections for grey areas)
  tds_acc        computed TDS equals expected (only where an expected amount exists)
  route_acc      auto/review matches expectation ('any' always passes)
  unsafe_auto    routed AUTO but section or amount wrong  <- the number that matters most
  missed_review  a case that should have reached a human but was auto-suggested
  review_rate    share of invoices sent to a human
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

from . import config, data
from .pipeline import process

RESULTS_DIR = config.ROOT / "eval" / "results"


def score(case: dict, r: dict) -> dict:
    exp = case["expected"]
    got = [c["code"] for c in r["classifications"]]
    accept = exp.get("accept_sections") or [[e] for e in exp["lines"]]
    section_ok = all(g in a for g, a in zip(got, accept))
    tds_ok = None if exp["tds_total"] is None else (r["tds_total"] == exp["tds_total"])
    return {
        "id": case["id"], "tag": case["tag"], "expected": exp["lines"], "got": got,
        "exp_tds": exp["tds_total"], "got_tds": r["tds_total"], "exp_route": exp["route"], "got_route": r["route"],
        "section_ok": section_ok, "strict_ok": got == exp["lines"], "tds_ok": tds_ok,
        "route_ok": exp["route"] in ("any", r["route"]),
        "unsafe_auto": r["route"] == "auto" and (not section_ok or tds_ok is False),
        "reasons": [x["code"] for x in r["reasons"]], "error": r["error"],
    }


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    tds_rows = [r for r in rows if r["tds_ok"] is not None]
    return {
        "cases": n,
        "section_acc": sum(r["section_ok"] for r in rows) / n,
        "strict_section_acc": sum(r["strict_ok"] for r in rows) / n,
        "tds_acc": sum(r["tds_ok"] for r in tds_rows) / len(tds_rows) if tds_rows else None,
        "route_acc": sum(r["route_ok"] for r in rows) / n,
        "unsafe_auto": sum(r["unsafe_auto"] for r in rows),
        "missed_review": sum(r["exp_route"] == "review" and r["got_route"] == "auto" for r in rows),
        "review_rate": sum(r["got_route"] == "review" for r in rows) / n,
        "errors": sum(bool(r["error"]) for r in rows),
    }


def to_markdown(title: str, summary: dict, rows: list[dict]) -> str:
    pct = lambda x: "-" if x is None else f"{x:.0%}"
    mark = lambda b: "-" if b is None else ("✅" if b else "❌")
    md = [f"# Eval: {title}", f"_Run {datetime.now():%Y-%m-%d %H:%M}_", "",
          "| metric | value |", "|---|---|",
          f"| cases | {summary['cases']} |",
          f"| section accuracy (grey areas accept any listed option) | {pct(summary['section_acc'])} |",
          f"| strict section accuracy | {pct(summary['strict_section_acc'])} |",
          f"| TDS amount accuracy (cases with an expected amount) | {pct(summary['tds_acc'])} |",
          f"| route accuracy | {pct(summary['route_acc'])} |",
          f"| **unsafe auto-suggestions** (auto + wrong) | **{summary['unsafe_auto']}** |",
          f"| missed reviews (should have gone to a human, went auto) | {summary['missed_review']} |",
          f"| review rate | {pct(summary['review_rate'])} |",
          f"| classifier errors | {summary['errors']} |", "",
          "| id | case | expected | got | sec | TDS exp/got | route exp/got | reasons |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['tag']} | {', '.join(r['expected'])} | {', '.join(r['got'])} | {mark(r['section_ok'])} "
                  f"| {r['exp_tds']} / {r['got_tds']} {mark(r['tds_ok'])} | {r['exp_route']} / {r['got_route']} {mark(r['route_ok'])}"
                  f"{' ⚠️UNSAFE' if r['unsafe_auto'] else ''} | {', '.join(r['reasons'])} |")
    return "\n".join(md) + "\n"


def run(mode: str = "baseline", samples: int = 1, model: str | None = None, case_ids: list[str] | None = None,
        delay: float = 0.0, out_dir: Path = RESULTS_DIR, log=print) -> dict:
    cases = data.test_cases()
    if case_ids:
        wanted = {c.upper() for c in case_ids}
        cases = [c for c in cases if c["id"] in wanted]
    model = model or config.OPENROUTER_MODEL

    rows = []
    for c in cases:
        r = process(c["invoice"], mode=mode, samples=samples, model=model, write_audit=False)
        s = score(c, r)
        rows.append(s)
        status = "ok " if s["section_ok"] and s["tds_ok"] is not False else "BAD"
        log(f"{c['id']} {status} got={s['got']} tds={s['got_tds']} route={s['got_route']}"
            f"{' UNSAFE' if s['unsafe_auto'] else ''}{' ERR ' + s['error'][:80] if s['error'] else ''}")
        if mode == "llm" and delay:
            time.sleep(delay)

    summary = summarise(rows)
    if mode == "baseline":
        tag, title = "baseline", "mode=baseline"
    else:
        tag = f"llm_{re.sub(r'[^a-zA-Z0-9]+', '-', model)}_s{samples}"
        title = f"mode=llm, model={model}, samples={samples}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{tag}.md").write_text(to_markdown(title, summary, rows), encoding="utf-8")
    (out_dir / f"{tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    return {"summary": summary, "rows": rows, "report": out_dir / f"{tag}.md"}
