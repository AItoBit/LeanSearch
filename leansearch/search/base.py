"""Shared machinery for all proof-search algorithms.

Every edge in the tree is a tactic that Lean actually executed. Solutions are
only accepted after independent replay by the verifier.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from leansearch.environment.base import ProofEnvironment, ProofVerifier
from leansearch.environment.lean_env import LeanSetupError
from leansearch.environment.proof_state import ProofState, Transition, VerificationResult
from leansearch.environment.repl import LeanProcessError
from leansearch.parsing.theorem_parser import Theorem, local_definitions
from leansearch.policy.base import PolicyContext, TacticPolicy
from leansearch.scoring.heuristic import HeuristicScorer, StateScorer
from leansearch.search.budget import BudgetTracker, SearchBudget
from leansearch.search.node import SearchNode, Status

log = logging.getLogger("leansearch.search")


@dataclass
class SearchResult:
    theorem: Theorem
    algorithm: str
    solved: bool
    stop_reason: str
    tactics: list[str] = field(default_factory=list)
    verification: VerificationResult | None = None
    stats: dict[str, object] = field(default_factory=dict)
    nodes: list[SearchNode] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    error: str | None = None

    @property
    def proof(self) -> str | None:
        return self.theorem.with_proof(self.tactics) if self.solved else None

    @property
    def root(self) -> SearchNode | None:
        return self.nodes[0] if self.nodes else None


class Searcher(ABC):
    algorithm = "base"

    def __init__(
        self,
        env: ProofEnvironment,
        policy: TacticPolicy,
        verifier: ProofVerifier | None = None,
        budget: SearchBudget | None = None,
        num_candidates: int = 8,
        scorer: StateScorer | None = None,
    ):
        self.env = env
        self.policy = policy
        self.verifier = verifier
        self.budget = budget or SearchBudget()
        self.num_candidates = num_candidates
        self.scorer = scorer or HeuristicScorer()

    # --------------------------------------------------------------- template

    def search(self, theorem: Theorem) -> SearchResult:
        self.theorem = theorem
        self._definitions = local_definitions(theorem.context)
        self.tracker = BudgetTracker(self.budget)
        self.nodes: list[SearchNode] = []
        self.transitions: list[Transition] = []
        self.seen: dict[str, SearchNode] = {}
        self.solution: SearchNode | None = None
        self.verification: VerificationResult | None = None
        self.rejected_solutions = 0

        calls_before = self.env.lean_calls
        try:
            root_state = self.env.start(theorem)
        except (LeanSetupError, LeanProcessError) as exc:
            return SearchResult(theorem, self.algorithm, False, "setup_error", error=str(exc),
                                stats=self._stats())
        self.tracker.lean_calls += self.env.lean_calls - calls_before

        root = self._new_node(root_state, None, None, 0.0)
        self.seen[root_state.state_id] = root
        log.info("THEOREM %s\n%s", theorem.name, root_state.pretty_state)
        self.run(root)

        solved = self.solution is not None
        stop = "solved" if solved else (self.tracker.exhausted() or "search_exhausted")
        tactics = list(self.solution.state.tactics) if self.solution else []
        return SearchResult(theorem, self.algorithm, solved, stop, tactics, self.verification,
                            self._stats(), self.nodes, self.transitions)

    @abstractmethod
    def run(self, root: SearchNode) -> None: ...

    def describe(self) -> dict[str, object]:
        return {"algorithm": self.algorithm, "num_candidates": self.num_candidates}

    # ---------------------------------------------------------------- helpers

    def done(self) -> bool:
        return self.solution is not None or self.tracker.exhausted() is not None

    def _new_node(self, state: ProofState, parent: SearchNode | None, action, policy_score: float) -> SearchNode:
        value = self.scorer.value(state)
        node = SearchNode(len(self.nodes), state, parent, action, policy_score, value, policy_score + value)
        self.nodes.append(node)
        if parent is not None:
            parent.children.append(node)
        return node

    def _context(self, node: SearchNode) -> PolicyContext:
        return PolicyContext(theorem=self.theorem.signature, definitions=self._definitions,
                             previous_tactics=list(node.state.tactics))

    def expand(self, node: SearchNode) -> list[SearchNode]:
        """Propose tactics for `node`, run each in Lean, and return new open children."""
        if node.depth >= self.budget.max_depth:
            node.status, node.note = Status.PRUNED, "max_depth"
            return []
        self.tracker.nodes += 1
        tokens_before = self.policy.tokens_used
        actions = self.policy.propose(node.state, self.num_candidates, self._context(node))
        self.tracker.tokens += self.policy.tokens_used - tokens_before
        node.status = Status.EXPANDED

        lines = [f"NODE {node.node_id} depth={node.depth} score={node.search_score:.3f}",
                 node.state.pretty_state, f"generated: {len(actions)}"]
        children: list[SearchNode] = []
        ancestors = node.ancestor_ids()
        for i, action in enumerate(actions, 1):
            if self.tracker.lean_calls >= self.budget.max_lean_calls:
                break
            calls_before = self.env.lean_calls
            tr = self.env.run_tactic(node.state, action)
            self.tracker.lean_calls += self.env.lean_calls - calls_before
            self.transitions.append(tr)
            if not tr.ok:
                lines.append(f"  {i}. {action.tactic!r} -> {tr.error_kind}")
                continue
            state = tr.result_state
            assert state is not None
            child = self._new_node(state, node, action, node.policy_score + (action.logprob or 0.0))
            if state.solved:
                lines.append(f"  {i}. {action.tactic!r} -> no goals")
                if self._accept(child):
                    break
            elif state.state_id == node.state.state_id:
                child.status, child.note = Status.PRUNED, "no_progress"
                lines.append(f"  {i}. {action.tactic!r} -> no progress")
            elif state.state_id in ancestors:
                child.status, child.note = Status.PRUNED, "cycle"
                lines.append(f"  {i}. {action.tactic!r} -> cycle")
            elif state.state_id in self.seen:
                child.status, child.note = Status.PRUNED, f"duplicate_of:{self.seen[state.state_id].node_id}"
                lines.append(f"  {i}. {action.tactic!r} -> duplicate of #{self.seen[state.state_id].node_id}")
            else:
                self.seen[state.state_id] = child
                children.append(child)
                lines.append(f"  {i}. {action.tactic!r} -> #{child.node_id} ({len(state.goals)} goals)")
        if not children and self.solution is None:
            node.status, node.note = Status.FAILED, "dead_end"
        log.info("\n".join(lines))
        return children

    def _accept(self, node: SearchNode) -> bool:
        if self.verifier is None:
            node.status = Status.SOLVED
            self.solution = node
            return True
        result = self.verifier.verify(self.theorem, node.state.tactics)
        self.verification = result
        if result.verified:
            node.status = Status.SOLVED
            self.solution = node
            return True
        self.rejected_solutions += 1
        node.status, node.note = Status.FAILED, "verification_failed"
        log.warning("proof rejected by independent replay: %s\n%s", node.state.tactics, result.messages)
        return False

    def _stats(self) -> dict[str, object]:
        valid = sum(1 for t in self.transitions if t.ok)
        pruned = [n.note or "" for n in self.nodes if n.status == Status.PRUNED]
        errors: dict[str, int] = {}
        for t in self.transitions:
            if t.error_kind:
                errors[t.error_kind] = errors.get(t.error_kind, 0) + 1
        expanded = [n for n in self.nodes if n.children]
        return {
            **self.tracker.to_dict(),
            "tree_nodes": len(self.nodes),
            "transitions": len(self.transitions),
            "valid_transitions": valid,
            "invalid_tactic_rate": round(1 - valid / len(self.transitions), 4) if self.transitions else 0.0,
            "duplicates": sum(1 for p in pruned if p.startswith("duplicate")),
            "cycles": pruned.count("cycle"),
            "no_progress": pruned.count("no_progress"),
            "max_depth_reached": max((n.depth for n in self.nodes), default=0),
            "branching_factor": round(sum(len(n.children) for n in expanded) / len(expanded), 3) if expanded else 0.0,
            "rejected_solutions": self.rejected_solutions,
            "error_kinds": errors,
            "policy_calls": self.policy.calls,
        }
