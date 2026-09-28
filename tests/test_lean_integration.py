"""Python -> Lean -> tactic -> new state, against a real REPL."""

import os

import pytest

from leansearch.environment.lean_env import LeanEnv, LeanSetupError
from leansearch.environment.repl import default_repl_path
from leansearch.environment.verifier import Verifier
from leansearch.parsing.theorem_parser import Theorem, parse_theorems
from leansearch.prover import LeanSearch

pytestmark = [
    pytest.mark.lean,
    pytest.mark.skipif(
        not default_repl_path().exists() and os.environ.get("LEANSEARCH_REPL_MODE") != "lean-run",
        reason="Lean REPL not built (run `lake build` in vendor/repl)",
    ),
]

SOURCE = """
def double : List Nat → List Nat
  | [] => []
  | x :: xs => (2 * x) :: double xs

theorem and_left (p q : Prop) : p ∧ q → p := by
  intro h; exact h.1

theorem double_length (l : List Nat) : (double l).length = l.length := by
  sorry

theorem nat_ok (n : Nat) (h : 0 < n) : n ≠ 0 := by
  omega
"""
AND_LEFT, DOUBLE_LENGTH, NAT_OK = parse_theorems(SOURCE)


@pytest.fixture(scope="module")
def env():
    with LeanEnv() as e:
        yield e


@pytest.fixture(scope="module")
def verifier():
    v = Verifier()
    yield v
    v.close()


def test_state_tactic_error_and_solve(env):
    s0 = env.start(AND_LEFT)
    assert s0.goals == ("p q : Prop\n⊢ p ∧ q → p",)

    tr = env.run_tactic(s0, "intro h")
    assert tr.ok and tr.result_state.local_context == ["p q : Prop", "h : p ∧ q"]
    s1 = tr.result_state

    bad = env.run_tactic(s1, "exact h.2")
    assert not bad.ok and bad.error_kind == "type_mismatch"
    unknown = env.run_tactic(s1, "frobnicate")
    assert not unknown.ok and unknown.error_kind in ("unknown_tactic", "syntax_error")

    done = env.run_tactic(s1, "exact h.1")
    assert done.ok and done.result_state.solved
    assert done.result_state.tactics == ("intro h", "exact h.1")


def test_states_are_persistent_branch_points(env):
    s0 = env.start(NAT_OK)
    a = env.run_tactic(s0, "intro hn").result_state
    b = env.run_tactic(s0, "omega").result_state
    assert b.solved and not a.solved
    assert env.run_tactic(a, "omega").result_state.solved


def test_forbidden_tactics_never_reach_lean(env):
    s0 = env.start(AND_LEFT)
    calls = env.lean_calls
    for t in ["sorry", "intro h; admit", "native_decide"]:
        tr = env.run_tactic(s0, t)
        assert not tr.ok and tr.error_kind == "forbidden"
    assert env.lean_calls == calls


def test_bad_statement_raises(env):
    with pytest.raises(LeanSetupError):
        env.start(Theorem("broken", 'theorem broken : (1 : Nat) = "one"'))


def test_recovers_state_after_process_crash(env):
    s0 = env.start(DOUBLE_LENGTH)
    s1 = env.run_tactic(s0, "induction l").result_state
    env.repl.close()
    env._restart()
    tr = env.run_tactic(s1, "simp [double]")
    assert tr.ok, tr.error
    assert env.restarts >= 1


def test_verifier_accepts_and_rejects(verifier):
    ok = verifier.verify(AND_LEFT, ["intro h", "exact h.1"])
    assert ok.verified, ok.messages
    wrong = verifier.verify(AND_LEFT, ["intro h", "exact h.2"])
    assert not wrong.verified
    incomplete = verifier.verify(AND_LEFT, ["intro h"])
    assert not incomplete.verified
    cheat = verifier.verify(AND_LEFT, ["sorry"])
    assert not cheat.verified


def test_verified_theorems_do_not_leak_into_later_checks(verifier):
    assert verifier.verify(AND_LEFT, ["intro h", "exact h.1"]).verified
    reuse = Theorem("uses_prev", "theorem uses_prev : True ∧ True → True")
    assert not verifier.verify(reuse, ["exact and_left True True"]).verified
    assert verifier.verify(reuse, ["intro h", "exact h.1"]).verified


def test_prover_end_to_end():
    with LeanSearch(search="best_first", max_nodes=50, num_candidates=10) as prover:
        result = prover.prove(DOUBLE_LENGTH)
    assert result.solved, result.stop_reason
    assert result.verification.verified
    assert result.proof.startswith("theorem double_length")


@pytest.mark.slow
def test_thousand_interactions_without_state_corruption(env):
    s0 = env.start(NAT_OK)
    s1 = env.run_tactic(s0, "intro hn").result_state
    for i in range(1000):
        base = s0 if i % 2 else s1
        tr = env.run_tactic(base, "omega" if i % 3 else "simp at *")
        again = env.run_tactic(base, "intro hn") if base is s0 else None
        if again is not None:
            assert again.ok and again.result_state.goals == s1.goals
        if i % 3:
            assert tr.ok and tr.result_state.solved, (i, tr.error)
