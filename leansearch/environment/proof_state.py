"""Core data structures shared by every layer of LeanSearch."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import cached_property
from typing import Any

from leansearch.parsing.normalize import state_hash
from leansearch.parsing.state_parser import Goal, parse_goal


@dataclass(frozen=True)
class ProofState:
    """A Lean tactic state, identified by the hash of its normalized goals.

    `tactics` is the path from the theorem's initial state, which is what makes
    a state replayable in a fresh Lean process.
    """

    goals: tuple[str, ...]
    tactics: tuple[str, ...] = ()
    handle: int = -1
    generation: int = 0

    @cached_property
    def state_id(self) -> str:
        return state_hash(self.goals)

    @property
    def depth(self) -> int:
        return len(self.tactics)

    @property
    def solved(self) -> bool:
        return not self.goals

    @property
    def pretty_state(self) -> str:
        return "\n\n".join(self.goals) if self.goals else "no goals"

    @cached_property
    def parsed_goals(self) -> tuple[Goal, ...]:
        return tuple(parse_goal(g) for g in self.goals)

    @property
    def local_context(self) -> list[str]:
        return [str(h) for h in self.parsed_goals[0].hypotheses] if self.goals else []

    def to_dict(self) -> dict[str, Any]:
        return {"state_id": self.state_id, "goals": list(self.goals), "depth": self.depth}


@dataclass(frozen=True)
class Action:
    tactic: str
    logprob: float | None = None
    source: str = "unknown"


@dataclass(frozen=True)
class Transition:
    state: ProofState
    action: Action
    result_state: ProofState | None
    error: str | None
    error_kind: str | None
    elapsed_ms: float

    @property
    def ok(self) -> bool:
        return self.result_state is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state.state_id,
            "depth": self.state.depth,
            "tactic": self.action.tactic,
            "logprob": self.action.logprob,
            "source": self.action.source,
            "result_state_id": self.result_state.state_id if self.result_state else None,
            "result_goals": list(self.result_state.goals) if self.result_state else None,
            "error": self.error,
            "error_kind": self.error_kind,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass
class VerificationResult:
    verified: bool
    proof: str
    messages: list[str] = field(default_factory=list)
    axioms: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
