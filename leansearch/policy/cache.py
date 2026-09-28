"""Candidate cache keyed by normalized state, for cheap reruns and deterministic debugging."""

from __future__ import annotations

import json
from pathlib import Path

from leansearch.environment.proof_state import Action, ProofState
from leansearch.policy.base import PolicyContext, TacticPolicy


class CachedPolicy(TacticPolicy):
    def __init__(self, inner: TacticPolicy, path: str | Path | None = None):
        super().__init__()
        self.inner = inner
        self.name = f"cached({inner.name})"
        self.path = Path(path) if path else None
        self.hits = 0
        self._cache: dict[str, list[dict[str, object]]] = {}
        if self.path and self.path.exists():
            self._cache = json.loads(self.path.read_text(encoding="utf-8"))

    def propose(self, state: ProofState, n: int, context: PolicyContext | None = None) -> list[Action]:
        key = f"{state.state_id}:{n}"
        if key in self._cache:
            self.hits += 1
            return [Action(**a) for a in self._cache[key]]  # type: ignore[arg-type]
        before = self.inner.tokens_used
        actions = self.inner.propose(state, n, context)
        self.calls += 1
        self.tokens_used += self.inner.tokens_used - before
        self._cache[key] = [{"tactic": a.tactic, "logprob": a.logprob, "source": a.source} for a in actions]
        return actions

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=1), encoding="utf-8")

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "inner": self.inner.describe(), "cache": str(self.path) if self.path else None}
