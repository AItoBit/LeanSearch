from __future__ import annotations

import enum
from dataclasses import dataclass, field

from leansearch.environment.proof_state import Action, ProofState


class Status(str, enum.Enum):
    OPEN = "OPEN"
    EXPANDED = "EXPANDED"
    FAILED = "FAILED"
    SOLVED = "SOLVED"
    PRUNED = "PRUNED"


@dataclass(eq=False)
class SearchNode:
    node_id: int
    state: ProofState
    parent: SearchNode | None = None
    action: Action | None = None
    policy_score: float = 0.0
    value_score: float = 0.0
    search_score: float = 0.0
    status: Status = Status.OPEN
    note: str | None = None
    children: list[SearchNode] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return self.state.depth

    def path(self) -> list[SearchNode]:
        node, out = self, []
        while node is not None:
            out.append(node)
            node = node.parent
        return out[::-1]

    def ancestor_ids(self) -> set[str]:
        return {n.state.state_id for n in self.path()}

    def to_dict(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "parent": self.parent.node_id if self.parent else None,
            "tactic": self.action.tactic if self.action else None,
            "state_id": self.state.state_id,
            "goals": list(self.state.goals),
            "depth": self.depth,
            "policy_score": round(self.policy_score, 4),
            "value_score": round(self.value_score, 4),
            "search_score": round(self.search_score, 4),
            "status": self.status.value,
            "note": self.note,
        }
