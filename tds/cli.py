"""Command line entry point.

  python -m tds.cli run --case T12                 # AI pipeline on a test case
  python -m tds.cli run --case T12 --mode baseline # keyword baseline only
  python -m tds.cli run --file my_invoice.json --samples 3
  python -m tds.cli search "hire of DG set"        # inspect retrieval
"""
import argparse
import json
import sys

from . import config
from .pipeline import process
from .retrieval import retrieve


def load_case(case_id: str) -> dict:
    cases = json.loads(config.TEST_CASES_PATH.read_text(encoding="utf-8"))["cases"]
    for c in cases:
        if c["id"].upper() == case_id.upper():
            return c["invoice"]
    sys.exit(f"unknown case {case_id}")


def print_result(r: dict) -> None:
    inv = r["invoice"]
    print(f"\nInvoice {inv.get('invoice_no')}  vendor {inv['vendor_id']} ({(r['vendor'] or {}).get('name', '?')})  date {inv['date']}")
    print(f"Mode: {r['mode']}   model: {r['model'] or '-'}   rules: {r['rule_set_id'] or 'NONE'}   kb: {r['kb_version']}")
    print("-" * 78)
    for cl, line, b in zip(r["classifications"], inv["lines"], r["baseline_codes"]):
        print(f"Line {cl['line']}: {line['description'][:70]}")
        print(f"   -> {cl['code']:<14} conf={cl['confidence']:<6} cites={cl['citations']}  keyword={b}")
        if cl.get("reasoning"):
            print(f"      {cl['reasoning']}")
    if r["engine"]:
        print("-" * 78)
        for s in r["engine"]["sections"]:
            for step in s["steps"]:
                print(f"   {step}")
    print("-" * 78)
    print(f"TDS total: {r['tds_total'] if r['tds_total'] is not None else 'NOT COMPUTED'}")
    print(f"Route: {r['route'].upper()}")
    for reason in r["reasons"]:
        print(f"   - [{reason['code']}] {reason['msg']}")
    if r.get("audit_id"):
        print(f"Audit record: {r['audit_id']}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="tds")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    g = run.add_mutually_exclusive_group(required=True)
    g.add_argument("--case")
    g.add_argument("--file")
    run.add_argument("--mode", choices=["llm", "baseline"], default="llm")
    run.add_argument("--samples", type=int, default=1)
    run.add_argument("--model", default=None)
    run.add_argument("--json", action="store_true", help="print the full result as JSON")
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=config.RETRIEVAL_TOP_K)
    args = p.parse_args(argv)

    if args.cmd == "search":
        for c in retrieve(args.query, args.k):
            print(f"{c['score']:>7}  {c['id']:<28} {c['authority']:<9} {c['title']}")
        return

    invoice = load_case(args.case) if args.case else json.loads(open(args.file, encoding="utf-8").read())
    r = process(invoice, mode=args.mode, samples=args.samples, model=args.model)
    if args.json:
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    else:
        print_result(r)


if __name__ == "__main__":
    main()
