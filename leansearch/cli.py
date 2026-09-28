"""Command-line interface.

  leansearch list  FILE.lean
  leansearch step  FILE.lean:NAME TACTIC [TACTIC ...]
  leansearch prove FILE.lean:NAME [--search beam --beam-width 8 ...]
  leansearch eval  PATH [PATH ...] [--out DIR ...]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from leansearch.environment.lean_env import LeanConfig, LeanEnv, LeanSetupError
from leansearch.environment.verifier import Verifier
from leansearch.experience.trajectory import TrajectoryWriter
from leansearch.parsing.theorem_parser import load_theorem, load_theorems
from leansearch.prover import LeanSearch, ProverConfig
from leansearch.search.algorithms import ALGORITHMS
from leansearch.search.budget import SearchBudget
from leansearch.search.export import tree_dot, tree_text


def _lean_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("lean")
    g.add_argument("--project", help="Lake project providing imports (must depend on REPL); default vendor/repl")
    g.add_argument("--repl", help="path to the compiled repl binary")
    g.add_argument("--repl-mode", choices=["auto", "binary", "lean-run"], default=None)
    g.add_argument("--tactic-timeout", type=float, default=30.0)


def _lean_config(a: argparse.Namespace) -> LeanConfig:
    return LeanConfig(repl_path=a.repl, project_dir=a.project, repl_mode=a.repl_mode, tactic_timeout=a.tactic_timeout)


def _prover_args(p: argparse.ArgumentParser) -> None:
    _lean_args(p)
    g = p.add_argument_group("search")
    g.add_argument("--search", choices=sorted(ALGORITHMS), default="beam")
    g.add_argument("--beam-width", type=int, default=8)
    g.add_argument("-k", "--candidates", type=int, default=8, help="tactics proposed per state")
    g.add_argument("--max-nodes", type=int, default=200, help="max state expansions")
    g.add_argument("--max-lean-calls", type=int, default=1000)
    g.add_argument("--max-depth", type=int, default=16)
    g.add_argument("--max-tokens", type=int, default=None)
    g.add_argument("--timeout", type=float, default=120.0, help="wall-clock seconds per theorem")
    g = p.add_argument_group("policy")
    g.add_argument("--policy", choices=["heuristic", "llm"], default="heuristic")
    g.add_argument("--mathlib", action="store_true", help="heuristic policy also tries Mathlib tactics")
    g.add_argument("--model", help="model name for --policy llm (OpenAI-compatible API)")
    g.add_argument("--base-url", help="API base URL, e.g. http://localhost:8000/v1 for vLLM")
    g.add_argument("--temperature", type=float, default=0.7)
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--candidate-cache", help="JSON file caching policy proposals per state")
    g.add_argument("--no-verify", action="store_true", help="skip independent replay (not recommended)")
    p.add_argument("-v", "--verbose", action="store_true", help="log every node expansion")


def _prover(a: argparse.Namespace) -> LeanSearch:
    budget = SearchBudget(a.max_nodes, a.max_lean_calls, a.max_depth, a.timeout, a.max_tokens)
    config = ProverConfig(
        search=a.search, beam_width=a.beam_width, num_candidates=a.candidates, budget=budget,
        policy=a.policy, mathlib=a.mathlib, model=a.model, base_url=a.base_url, temperature=a.temperature,
        seed=a.seed, candidate_cache=a.candidate_cache, verify=not a.no_verify, lean=_lean_config(a),
    )
    return LeanSearch(config)


def cmd_list(a: argparse.Namespace) -> int:
    for thm in load_theorems(a.file):
        print(f"{thm.line:5d}  {thm.name}")
    return 0


def cmd_step(a: argparse.Namespace) -> int:
    theorem = load_theorem(a.theorem)
    with LeanEnv(_lean_config(a)) as env:
        t0 = time.perf_counter()
        try:
            state = env.start(theorem)
        except LeanSetupError as exc:
            print(f"setup error: {exc}", file=sys.stderr)
            return 2
        print(f"[{theorem.name}] initial state ({(time.perf_counter() - t0):.2f}s, repl={env.repl.mode}):")
        print(state.pretty_state)
        for tactic in a.tactics:
            tr = env.run_tactic(state, tactic)
            print(f"\n>>> {tactic}   ({tr.elapsed_ms:.0f} ms)")
            if not tr.ok:
                print(f"ERROR [{tr.error_kind}]\n{tr.error}")
                return 1
            state = tr.result_state
            print(state.pretty_state)
    if not state.solved:
        print("\n(goals remain)")
        return 1
    result = Verifier(_lean_config(a), fresh_process=True).verify(theorem, state.tactics)
    print(f"\nIndependent replay in a fresh Lean process: {'VERIFIED' if result.verified else 'REJECTED'}"
          f" ({result.elapsed_ms / 1000:.2f}s, axioms: {result.axioms or 'none'})")
    for m in result.messages:
        print(m)
    print("\n" + result.proof)
    return 0 if result.verified else 1


def cmd_prove(a: argparse.Namespace) -> int:
    theorem = load_theorem(a.theorem)
    with _prover(a) as prover:
        print(f"Theorem {theorem.name}  ({prover.config.search}, policy={prover.policy.name})")
        result = prover.prove(theorem)
    if result.error:
        print(f"setup error: {result.error}", file=sys.stderr)
        return 2
    if result.root is not None:
        print("\nGoal:\n" + result.root.state.pretty_state + "\n")
    if a.tree:
        print(tree_text(result, show_errors=a.tree_errors) + "\n")
    if a.dot:
        Path(a.dot).write_text(tree_dot(result), encoding="utf-8")
    if a.trajectories:
        TrajectoryWriter(a.trajectories).write(result)
    s = result.stats
    if result.solved:
        print("PROOF FOUND (verified by independent replay)\n" if result.verification else "PROOF FOUND\n")
        print(result.proof + "\n")
    else:
        print(f"NOT SOLVED (stop reason: {result.stop_reason})\n")
    print(f"Nodes expanded: {s['nodes']}   tree size: {s['tree_nodes']}   Lean calls: {s['lean_calls']}")
    print(f"Depth: {len(result.tactics) if result.solved else s['max_depth_reached']}   "
          f"duplicates pruned: {s['duplicates']}   invalid tactic rate: {s['invalid_tactic_rate']:.0%}")
    print(f"Time: {s['elapsed_s']:.2f} s   tokens: {s['tokens']}")
    return 0 if result.solved else 1


def cmd_eval(a: argparse.Namespace) -> int:
    from leansearch.evaluation.runner import collect_theorems, evaluate

    theorems = collect_theorems(a.paths)
    if a.limit:
        theorems = theorems[: a.limit]
    out = a.out or f"reports/benchmark_results/{datetime.now():%Y%m%d-%H%M%S}-{a.search}-{a.policy}"

    def show(i: int, r) -> None:
        mark = "✓" if r.solved else "✗"
        detail = " ; ".join(r.tactics) if r.solved else r.stop_reason
        print(f"[{i + 1:3d}/{len(theorems)}] {mark} {r.theorem.name:<32} {r.stats.get('lean_calls', 0):5} calls  "
              f"{r.stats.get('elapsed_s', 0):6.2f}s  {detail}", flush=True)

    with _prover(a) as prover:
        summary = evaluate(prover, theorems, out, on_result=show)
    print(json.dumps(summary["summary"], indent=2))
    print(f"\nWrote {out}/summary.json and {out}/trajectories.jsonl")
    solved = summary["summary"]["solved"]
    if a.min_solved is not None and solved < a.min_solved:
        print(f"REGRESSION: solved {solved} < required {a.min_solved}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="leansearch", description="Search-based theorem proving for Lean 4")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list theorems in a Lean file")
    p.add_argument("file")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("step", help="apply tactics one by one and replay the finished proof")
    p.add_argument("theorem", help="FILE.lean:NAME")
    p.add_argument("tactics", nargs="*")
    _lean_args(p)
    p.set_defaults(fn=cmd_step)

    p = sub.add_parser("prove", help="search for a proof of one theorem")
    p.add_argument("theorem", help="FILE.lean:NAME")
    p.add_argument("--tree", action="store_true", help="print the search tree")
    p.add_argument("--tree-errors", action="store_true", help="include failed tactics in --tree")
    p.add_argument("--dot", help="write the search tree as Graphviz DOT")
    p.add_argument("--trajectories", help="append the run to this JSONL file")
    _prover_args(p)
    p.set_defaults(fn=cmd_prove)

    p = sub.add_parser("eval", help="evaluate on a benchmark (files or directories)")
    p.add_argument("paths", nargs="+")
    p.add_argument("--out", help="output directory")
    p.add_argument("--limit", type=int)
    p.add_argument("--min-solved", type=int, help="exit non-zero if fewer theorems are solved (regression gate)")
    _prover_args(p)
    p.set_defaults(fn=cmd_eval)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
                        format="%(message)s")
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
