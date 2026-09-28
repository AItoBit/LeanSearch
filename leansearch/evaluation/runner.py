"""Benchmark evaluation under fixed budgets, with full run metadata."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from leansearch.environment.lean_env import lean_toolchain
from leansearch.experience.trajectory import TrajectoryWriter
from leansearch.parsing.theorem_parser import Theorem, load_theorems
from leansearch.prover import LeanSearch
from leansearch.search.base import SearchResult


def git_commit() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, timeout=10)
        return {"commit": commit.stdout.strip() or None, "dirty": bool(dirty.stdout.strip())}
    except (OSError, subprocess.TimeoutExpired):
        return {"commit": None, "dirty": None}


def run_metadata(prover: LeanSearch) -> dict[str, Any]:
    return {
        **git_commit(),
        "lean": lean_toolchain(prover.config.lean),
        "repl_mode": prover.env.repl.mode,
        "config": prover.config.to_dict(),
        "policy": prover.policy.describe(),
        "search": prover.searcher.describe(),
        "scorer": prover.searcher.scorer.describe(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def collect_theorems(paths: list[str]) -> list[Theorem]:
    theorems: list[Theorem] = []
    for p in paths:
        path = Path(p)
        files = sorted(path.rglob("*.lean")) if path.is_dir() else [path]
        for f in files:
            theorems += load_theorems(f)
    return theorems


def summarize(results: list[SearchResult]) -> dict[str, Any]:
    n = len(results)
    solved = [r for r in results if r.solved]

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    return {
        "theorems": n,
        "solved": len(solved),
        "solved_pct": round(100 * len(solved) / n, 2) if n else 0.0,
        "setup_errors": sum(1 for r in results if r.stop_reason == "setup_error"),
        "lean_calls_total": sum(int(r.stats.get("lean_calls", 0)) for r in results),
        "lean_calls_per_solved": mean([float(r.stats["lean_calls"]) for r in solved]),
        "nodes_per_solved": mean([float(r.stats["nodes"]) for r in solved]),
        "tokens_total": sum(int(r.stats.get("tokens", 0)) for r in results),
        "time_total_s": round(sum(float(r.stats.get("elapsed_s", 0)) for r in results), 2),
        "time_per_solved_s": mean([float(r.stats["elapsed_s"]) for r in solved]),
        "avg_proof_length": mean([float(len(r.tactics)) for r in solved]),
        "invalid_tactic_rate": mean([float(r.stats.get("invalid_tactic_rate", 0)) for r in results]),
        "stop_reasons": {k: sum(1 for r in results if r.stop_reason == k) for k in {r.stop_reason for r in results}},
    }


def evaluate(
    prover: LeanSearch,
    theorems: list[Theorem],
    out_dir: str | Path,
    on_result: Callable[[int, SearchResult], None] | None = None,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    writer = TrajectoryWriter(out / "trajectories.jsonl")
    results: list[SearchResult] = []
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.perf_counter()
    for i, thm in enumerate(theorems):
        result = prover.prove(thm)
        results.append(result)
        writer.write(result, {"run_dir": str(out)})
        if on_result:
            on_result(i, result)
    summary = {
        "meta": {**run_metadata(prover), "started_at": started},
        "wall_time_s": round(time.perf_counter() - t0, 2),
        "summary": summarize(results),
        "per_theorem": [
            {"name": r.theorem.name, "source": r.theorem.source, "solved": r.solved, "stop_reason": r.stop_reason,
             "tactics": r.tactics, "lean_calls": r.stats.get("lean_calls"), "nodes": r.stats.get("nodes"),
             "elapsed_s": r.stats.get("elapsed_s"), "error": r.error}
            for r in results
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
