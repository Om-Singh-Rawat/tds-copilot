"""Thin wrapper kept for convenience; the logic lives in tds/evaluation.py.

  python eval/run_eval.py --mode baseline
  python eval/run_eval.py --mode llm --delay 3          # needs OPENROUTER_API_KEY
  python eval/run_eval.py --mode llm --samples 3 --cases T12,T13

Same as:  python -m tds eval ...
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tds.cli import main  # noqa: E402

if __name__ == "__main__":
    main(["eval", *sys.argv[1:]])
