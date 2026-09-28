"""A deterministic toy environment: the goal `⊢ P n` is solved when n reaches 0."""

from __future__ import annotations

from leansearch.environment.proof_state import Action, ProofState, Transition, VerificationResult
from leansearch.parsing.theorem_parser import Theorem
from leansearch.policy.base import PolicyContext, TacticPolicy, rank_logprobs

THEOREM = Theorem(name="toy", signature="theorem toy : P 5")


def goal(n: int) -> str:
    return f"x : Nat\n⊢ P {n}"


class FakeEnv:
    """Tactics: `sub k` (n -> n-k, error if k > n), `add k` (n -> n+k),
    `noop`, `bad` (always errors)."""

    def __init__(self, start: int = 5):
        self.start_n = start
        self.lean_calls = 0

    def start(self, theorem: Theorem) -> ProofState:
        self.lean_calls += 1
        return ProofState((goal(self.start_n),))

    def run_tactic(self, state: ProofState, action: Action | str) -> Transition:
        if isinstance(action, str):
            action = Action(action)
        self.lean_calls += 1
        n = int(state.goals[0].rsplit(" ", 1)[1])
        op, *arg = action.tactic.split()
        k = int(arg[0]) if arg else 0
        if op == "bad" or (op == "sub" and k > n):
            return Transition(state, action, None, "tactic failed", "tactic_failed", 0.0)
        m = {"sub": n - k, "add": n + k, "noop": n}[op]
        goals = () if m == 0 else (goal(m),)
        return Transition(state, action, ProofState(goals, state.tactics + (action.tactic,)), None, None, 0.0)

    def close(self) -> None:
        pass


class FixedPolicy(TacticPolicy):
    name = "fixed"

    def __init__(self, tactics: list[str]):
        super().__init__()
        self.tactics = tactics

    def propose(self, state: ProofState, n: int, context: PolicyContext | None = None) -> list[Action]:
        self.calls += 1
        chosen = self.tactics[:n]
        return [Action(t, lp, "fixed") for t, lp in zip(chosen, rank_logprobs(len(chosen)))]


class FakeVerifier:
    def __init__(self, accept: bool = True):
        self.accept = accept
        self.calls = 0

    def verify(self, theorem: Theorem, tactics) -> VerificationResult:
        self.calls += 1
        return VerificationResult(self.accept, theorem.with_proof(tactics))
