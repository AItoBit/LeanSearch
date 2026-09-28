from __future__ import annotations

import time
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SearchBudget:
    max_nodes: int = 1000
    max_lean_calls: int = 500
    max_depth: int = 32
    timeout_seconds: float = 120.0
    max_tokens: int | None = None


class BudgetTracker:
    def __init__(self, budget: SearchBudget):
        self.budget = budget
        self.start = time.perf_counter()
        self.nodes = 0
        self.lean_calls = 0
        self.tokens = 0

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.start

    def exhausted(self) -> str | None:
        """Name of the first exhausted resource, or None."""
        b = self.budget
        if self.nodes >= b.max_nodes:
            return "max_nodes"
        if self.lean_calls >= b.max_lean_calls:
            return "max_lean_calls"
        if self.elapsed >= b.timeout_seconds:
            return "timeout"
        if b.max_tokens is not None and self.tokens >= b.max_tokens:
            return "max_tokens"
        return None

    def to_dict(self) -> dict[str, object]:
        return {"budget": asdict(self.budget), "nodes": self.nodes, "lean_calls": self.lean_calls,
                "tokens": self.tokens, "elapsed_s": round(self.elapsed, 3)}
