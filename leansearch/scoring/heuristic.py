"""Hand-written state scores; the slot a learned value model will later fill."""

from __future__ import annotations

from dataclasses import dataclass

from leansearch.environment.proof_state import ProofState


class StateScorer:
    def value(self, state: ProofState) -> float:
        raise NotImplementedError

    def describe(self) -> dict[str, object]:
        return {"name": type(self).__name__}


@dataclass
class HeuristicScorer(StateScorer):
    """score = cumulative policy logprob + value, with value penalizing depth,
    open goals and goal size."""

    depth_weight: float = 0.1
    goals_weight: float = 0.3
    size_weight: float = 0.002

    def value(self, state: ProofState) -> float:
        if state.solved:
            return 0.0
        size = sum(len(g.target) for g in state.parsed_goals)
        return -(self.depth_weight * state.depth + self.goals_weight * len(state.goals) + self.size_weight * size)

    def describe(self) -> dict[str, object]:
        return {"name": "heuristic", "depth_weight": self.depth_weight,
                "goals_weight": self.goals_weight, "size_weight": self.size_weight}
