"""Run several search configurations on the same benchmark under identical budgets.

  python scripts/run_matrix.py benchmarks/mini --max-nodes 50 --max-lean-calls 400
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from leansearch.evaluation.runner import collect_theorems, evaluate  # noqa: E402
from leansearch.prover import LeanSearch, ProverConfig  # noqa: E402
from leansearch.search.budget import SearchBudget  # noqa: E402

MATRIX = [
    ("Greedy", {"search": "greedy"}),
    ("BFS", {"search": "bfs"}),
    ("Beam-4", {"search": "beam", "beam_width": 4}),
    ("Beam-8", {"search": "beam", "beam_width": 8}),
    ("Beam-16", {"search": "beam", "beam_width": 16}),
    ("Best-first", {"search": "best_first"}),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--max-nodes", type=int, default=50)
    ap.add_argument("--max-lean-calls", type=int, default=400)
    ap.add_argument("--max-depth", type=int, default=12)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("-k", "--candidates", type=int, default=10)
    ap.add_argument("--policy", default="heuristic")
    ap.add_argument("--model")
    ap.add_argument("--out")
    args = ap.parse_args()

    theorems = collect_theorems(args.paths)
    out = Path(args.out or f"reports/benchmark_results/matrix-{datetime.now():%Y%m%d-%H%M%S}")
    budget = SearchBudget(args.max_nodes, args.max_lean_calls, args.max_depth, args.timeout)
    rows = []
    for label, overrides in MATRIX:
        config = ProverConfig(budget=budget, num_candidates=args.candidates, policy=args.policy,
                              model=args.model, **overrides)
        with LeanSearch(config) as prover:
            summary = evaluate(prover, theorems, out / label.lower())
        s = summary["summary"]
        rows.append((label, s))
        print(f"{label:<11} solved {s['solved']:3d}/{s['theorems']}  lean calls {s['lean_calls_total']:6d}  "
              f"time {s['time_total_s']:7.2f}s", flush=True)

    lines = [
        f"Benchmark: {', '.join(args.paths)} ({len(theorems)} theorems), policy={args.policy}, k={args.candidates}, "
        f"budget: {args.max_nodes} expansions / {args.max_lean_calls} Lean calls / depth {args.max_depth} "
        f"/ {args.timeout:.0f}s per theorem",
        "",
        "| Method | Solved | Solved % | Lean calls (total) | Lean calls / solved | Expansions / solved "
        "| Avg proof length | Time (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, s in rows:
        lines.append(
            f"| {label} | {s['solved']}/{s['theorems']} | {s['solved_pct']} | {s['lean_calls_total']} "
            f"| {s['lean_calls_per_solved']} | {s['nodes_per_solved']} | {s['avg_proof_length']} "
            f"| {s['time_total_s']} |"
        )
    table = "\n".join(lines)
    (out / "table.md").write_text(table + "\n", encoding="utf-8")
    (out / "matrix.json").write_text(json.dumps(dict(rows), indent=2), encoding="utf-8")
    print("\n" + table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
