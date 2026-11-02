"""Run the 21 synthetic test cases and write an honest scorecard.

  python eval/run_eval.py --mode baseline
  python eval/run_eval.py --mode llm --delay 4          # needs OPENROUTER_API_KEY
  python eval/run_eval.py --mode llm --samples 3 --cases T12,T13

Metrics
  section_acc   every line's code is acceptable (expected, or in accept_sections for grey areas)
  tds_acc       computed TDS equals expected (only where an expected amount exists)
  route_acc     auto/review matches expectation ('any' always passes)
  unsafe_auto   routed AUTO but section or amount wrong  <- the number that matters most
  missed_review a grey-area case that should have reached a human but was auto-suggested
  review_rate   share of invoices sent to a human
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tds import config  # noqa: E402
from tds.pipeline import process  # noqa: E402

OUT = ROOT / "eval" / "results"


def score(case: dict, r: dict) -> dict:
    exp = case["expected"]
    got = [c["code"] for c in r["classifications"]]
    accept = exp.get("accept_sections") or [[e] for e in exp["lines"]]
    section_ok = all(g in a for g, a in zip(got, accept))
    strict_ok = got == exp["lines"]
    tds_ok = None if exp["tds_total"] is None else (r["tds_total"] == exp["tds_total"])
    route_ok = exp["route"] == "any" or exp["route"] == r["route"]
    unsafe = r["route"] == "auto" and (not section_ok or tds_ok is False)
    return {"id": case["id"], "tag": case["tag"], "expected": exp["lines"], "got": got,
            "exp_tds": exp["tds_total"], "got_tds": r["tds_total"], "exp_route": exp["route"], "got_route": r["route"],
            "section_ok": section_ok, "strict_ok": strict_ok, "tds_ok": tds_ok, "route_ok": route_ok,
            "unsafe_auto": unsafe, "reasons": [x["code"] for x in r["reasons"]], "error": r["error"]}


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


def to_markdown(mode: str, model: str, samples: int, summary: dict, rows: list[dict]) -> str:
    pct = lambda x: "-" if x is None else f"{x:.0%}"
    mark = lambda b: "-" if b is None else ("✅" if b else "❌")
    md = [f"# Eval: mode={mode}" + (f", model={model}, samples={samples}" if mode == "llm" else ""),
          f"_Run {datetime.now():%Y-%m-%d %H:%M}_", "",
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["llm", "baseline"], default="baseline")
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--model", default=None)
    p.add_argument("--cases", default="", help="comma separated ids, default all")
    p.add_argument("--delay", type=float, default=0.0, help="seconds to wait between LLM calls (free-tier rate limits)")
    args = p.parse_args()

    cases = json.loads(config.TEST_CASES_PATH.read_text(encoding="utf-8"))["cases"]
    if args.cases:
        wanted = {c.strip().upper() for c in args.cases.split(",")}
        cases = [c for c in cases if c["id"] in wanted]

    model = args.model or config.OPENROUTER_MODEL
    rows = []
    for c in cases:
        r = process(c["invoice"], mode=args.mode, samples=args.samples, model=model, write_audit=False)
        s = score(c, r)
        rows.append(s)
        status = "ok " if s["section_ok"] and s["tds_ok"] is not False else "BAD"
        print(f"{c['id']} {status} got={s['got']} tds={s['got_tds']} route={s['got_route']}"
              f"{' UNSAFE' if s['unsafe_auto'] else ''}{' ERR ' + s['error'][:80] if s['error'] else ''}")
        if args.mode == "llm" and args.delay:
            time.sleep(args.delay)

    summary = summarise(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = args.mode if args.mode == "baseline" else f"llm_{re.sub(r'[^a-zA-Z0-9]+', '-', model)}_s{args.samples}"
    (OUT / f"{tag}.md").write_text(to_markdown(args.mode, model, args.samples, summary, rows), encoding="utf-8")
    (OUT / f"{tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, indent=2))
    print(f"report: {OUT / (tag + '.md')}")


if __name__ == "__main__":
    main()
