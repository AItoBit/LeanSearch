"""Serialize search runs (successful and failed) as JSONL training/analysis records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from leansearch.search.base import SearchResult
from leansearch.search.node import Status


def result_record(result: SearchResult, meta: dict[str, Any] | None = None, include_tree: bool = True) -> dict[str, Any]:
    thm = result.theorem
    path = []
    solution = next((n for n in result.nodes if n.status == Status.SOLVED), None)
    if solution is not None:
        steps = solution.path()
        path = [{"state_id": s.state.state_id, "goals": list(s.state.goals), "tactic": nxt.action.tactic}
                for s, nxt in zip(steps, steps[1:]) if nxt.action is not None]
    record: dict[str, Any] = {
        "theorem": {"name": thm.name, "source": thm.source, "line": thm.line, "signature": thm.signature,
                    "context_chars": len(thm.context)},
        "algorithm": result.algorithm,
        "solved": result.solved,
        "verified": bool(result.verification and result.verification.verified),
        "reward": 1 if result.solved else 0,
        "stop_reason": result.stop_reason,
        "proof": result.proof,
        "tactics": result.tactics,
        "success_path": path,
        "stats": result.stats,
        "error": result.error,
        "meta": meta or {},
    }
    if result.verification is not None:
        record["verification"] = result.verification.to_dict()
    if include_tree:
        record["nodes"] = [n.to_dict() for n in result.nodes]
        record["transitions"] = [t.to_dict() for t in result.transitions]
    return record


class TrajectoryWriter:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, result: SearchResult, meta: dict[str, Any] | None = None) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(result_record(result, meta), ensure_ascii=False) + "\n")


def read_trajectories(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
