from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from leansearch.environment.proof_state import Action, ProofState


@dataclass
class PolicyContext:
    """Extra information a policy may condition on besides the proof state."""

    theorem: str = ""
    definitions: list[str] = field(default_factory=list)
    premises: list[str] = field(default_factory=list)
    previous_tactics: list[str] = field(default_factory=list)
    feedback: list[str] = field(default_factory=list)


class TacticPolicy(ABC):
    """Proposes candidate tactics for a proof state. Never decides validity."""

    name: str = "policy"

    def __init__(self) -> None:
        self.tokens_used = 0
        self.calls = 0

    @abstractmethod
    def propose(self, state: ProofState, n: int, context: PolicyContext | None = None) -> list[Action]: ...

    def describe(self) -> dict[str, object]:
        return {"name": self.name}


def rank_logprobs(n: int) -> list[float]:
    """Harmonic prior over ranks for policies that give an ordering but no probabilities."""
    weights = [1.0 / (i + 1) for i in range(n)]
    total = sum(weights)
    return [math.log(w / total) for w in weights]


def dedupe_actions(actions: list[Action], n: int) -> list[Action]:
    seen: set[str] = set()
    out: list[Action] = []
    for a in actions:
        key = " ".join(a.tactic.split())
        if key and key not in seen:
            seen.add(key)
            out.append(a)
        if len(out) == n:
            break
    return out
