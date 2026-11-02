"""Command line entry point (`python -m tds ...`, or `tds ...` after `pip install .`).

  python -m tds run --case T12                  # AI pipeline on a test case
  python -m tds run --case T12 --mode baseline  # keyword baseline only
  python -m tds run --file my_invoice.json --samples 3
  python -m tds search "hire of DG set"         # inspect retrieval
  python -m tds eval --mode llm --delay 3       # score the test set
  python -m tds serve --port 8000               # reviewer UI
"""
import argparse
import json
import sys
from pathlib import Path

from . import config, data
from .schema import InvalidInvoice


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


def cmd_run(args) -> None:
    from .pipeline import process
    if args.case:
        case = data.test_case(args.case)
        if case is None:
            sys.exit(f"unknown case {args.case}")
        invoice = case["invoice"]
    else:
        with open(args.file, encoding="utf-8") as f:
            invoice = json.load(f)
    try:
        r = process(invoice, mode=args.mode, samples=args.samples, model=args.model)
    except InvalidInvoice as e:
        sys.exit("invalid invoice:\n  - " + "\n  - ".join(e.errors))
    if args.json:
        print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    else:
        print_result(r)


def cmd_search(args) -> None:
    from .retrieval import retrieve
    for c in retrieve(args.query, args.k):
        print(f"{c['score']:>7}  {c['id']:<28} {c['authority']:<9} {c['title']}")


def cmd_eval(args) -> None:
    from .evaluation import run
    cases = [c.strip() for c in args.cases.split(",") if c.strip()] if args.cases else None
    kwargs = {"out_dir": Path(args.out)} if args.out else {}
    res = run(mode=args.mode, samples=args.samples, model=args.model, case_ids=cases, delay=args.delay, **kwargs)
    print("\n" + json.dumps(res["summary"], indent=2))
    print(f"report: {res['report']}")


def cmd_serve(args) -> None:
    from .web import serve
    serve(args.host, args.port)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tds", description="TDS Copilot - AI-assisted TDS classification")
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="classify one invoice and compute TDS")
    g = run.add_mutually_exclusive_group(required=True)
    g.add_argument("--case", help="test case id, e.g. T12")
    g.add_argument("--file", help="path to an invoice JSON file")
    run.add_argument("--mode", choices=["llm", "baseline"], default="llm")
    run.add_argument("--samples", type=int, default=1, help="self-consistency samples (1-5)")
    run.add_argument("--model", default=None)
    run.add_argument("--json", action="store_true", help="print the full result as JSON")
    run.set_defaults(func=cmd_run)

    s = sub.add_parser("search", help="show what retrieval returns for a query")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=config.RETRIEVAL_TOP_K)
    s.set_defaults(func=cmd_search)

    e = sub.add_parser("eval", help="score the synthetic test set")
    e.add_argument("--mode", choices=["llm", "baseline"], default="baseline")
    e.add_argument("--samples", type=int, default=1)
    e.add_argument("--model", default=None)
    e.add_argument("--cases", default="", help="comma separated ids, default all")
    e.add_argument("--delay", type=float, default=0.0, help="seconds between LLM calls (free-tier limits)")
    e.add_argument("--out", default=None, help="results directory (default eval/results)")
    e.set_defaults(func=cmd_eval)

    w = sub.add_parser("serve", help="start the reviewer web UI")
    w.add_argument("--host", default=config.HOST)
    w.add_argument("--port", type=int, default=config.PORT)
    w.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
