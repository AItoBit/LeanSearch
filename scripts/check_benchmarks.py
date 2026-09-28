"""Check that benchmark files compile with their reference proofs and parse into theorems.

  python scripts/check_benchmarks.py benchmarks/mini
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leansearch.environment.repl import ReplProcess  # noqa: E402
from leansearch.parsing.theorem_parser import load_theorems  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--project")
    args = ap.parse_args()

    files = [f for p in map(Path, args.paths) for f in (sorted(p.rglob("*.lean")) if p.is_dir() else [p])]
    failed = 0
    with ReplProcess(project_dir=args.project) as repl:
        for f in files:
            resp = repl.send({"cmd": f.read_text(encoding="utf-8")}, timeout=600)
            errors = [f"line {m['pos']['line']}: {m['data']}" for m in resp.get("messages", [])
                      if m.get("severity") == "error"] or ([resp["message"]] if "message" in resp else [])
            sorry = [m for m in resp.get("messages", []) if "sorry" in m.get("data", "")]
            n = len(load_theorems(f))
            ok = not errors and not sorry
            failed += not ok
            print(f"{'OK  ' if ok else 'FAIL'} {f}  ({n} theorems)")
            for e in errors:
                print("   ", e.replace("\n", "\n    "))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
