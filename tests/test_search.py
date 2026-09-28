import pytest

from leansearch.search.algorithms import ALGORITHMS, BeamSearch, BestFirstSearch, GreedySearch
from leansearch.search.budget import SearchBudget
from leansearch.search.export import tree_dot, tree_text
from leansearch.search.node import Status
from tests.fakes import THEOREM, FakeEnv, FakeVerifier, FixedPolicy


def make(cls, tactics, budget=None, verifier=None, start=5, **kw):
    return cls(FakeEnv(start), FixedPolicy(tactics), verifier or FakeVerifier(), budget or SearchBudget(), 8, **kw)


@pytest.mark.parametrize("name", sorted(ALGORITHMS))
def test_every_algorithm_solves_toy_problem(name):
    result = make(ALGORITHMS[name], ["sub 2", "sub 1", "bad"]).search(THEOREM)
    assert result.solved and result.stop_reason == "solved"
    assert result.verification is not None and result.verification.verified
    n = 5
    for t in result.tactics:
        n -= int(t.split()[1])
    assert n == 0


def test_greedy_follows_top_ranked_tactic():
    result = make(GreedySearch, ["sub 1", "add 7"]).search(THEOREM)
    assert result.tactics == ["sub 1"] * 5


def test_greedy_skips_states_already_seen_elsewhere():
    # From 4, `sub 1` reaches 3, which the root expansion already produced via `sub 2`.
    result = make(GreedySearch, ["sub 1", "sub 2"]).search(THEOREM)
    assert result.tactics == ["sub 1", "sub 2", "sub 2"]


def test_greedy_has_no_backtracking():
    # `add 1` is ranked first and always valid, so greedy never reaches 0 before max_depth.
    result = make(GreedySearch, ["add 1", "sub 5"], start=5, budget=SearchBudget(max_depth=3)).search(THEOREM)
    assert result.solved  # `sub 5` at the root solves immediately
    result = make(GreedySearch, ["add 1", "sub 9"], budget=SearchBudget(max_depth=3)).search(THEOREM)
    assert not result.solved


def test_noop_cycles_and_duplicates_are_pruned():
    result = make(BestFirstSearch, ["noop", "add 1", "sub 1"], budget=SearchBudget(max_nodes=50)).search(THEOREM)
    assert result.solved
    notes = [n.note for n in result.nodes if n.status == Status.PRUNED]
    assert "no_progress" in notes and "cycle" in notes
    assert result.stats["cycles"] > 0 and result.stats["no_progress"] > 0


def test_transposition_table_deduplicates_states():
    # sub 1 then sub 2 and sub 2 then sub 1 reach the same state.
    result = make(BeamSearch, ["sub 1", "sub 2"], beam_width=8, start=6).search(THEOREM)
    assert result.solved
    assert result.stats["duplicates"] > 0
    ids = [n.state.state_id for n in result.nodes if n.status in (Status.OPEN, Status.EXPANDED)]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("name", sorted(ALGORITHMS))
def test_budget_limits_are_respected(name):
    budget = SearchBudget(max_nodes=4, max_lean_calls=1000)
    result = make(ALGORITHMS[name], ["add 1", "add 2", "add 3"], budget=budget).search(THEOREM)
    assert not result.solved
    assert result.stats["nodes"] <= 4

    budget = SearchBudget(max_nodes=1000, max_lean_calls=7)
    result = make(ALGORITHMS[name], ["add 1", "add 2", "add 3"], budget=budget).search(THEOREM)
    assert result.stats["lean_calls"] <= 7
    assert result.stop_reason == "max_lean_calls"


def test_max_depth_prunes():
    result = make(BestFirstSearch, ["sub 1"], budget=SearchBudget(max_depth=3)).search(THEOREM)
    assert not result.solved
    assert any(n.note == "max_depth" for n in result.nodes)


def test_rejected_solution_is_not_reported():
    result = make(BestFirstSearch, ["sub 5"], verifier=FakeVerifier(accept=False)).search(THEOREM)
    assert not result.solved
    assert result.stats["rejected_solutions"] == 1
    assert any(n.note == "verification_failed" for n in result.nodes)


def test_exports():
    result = make(BeamSearch, ["sub 2", "sub 3", "bad"]).search(THEOREM)
    text = tree_text(result, show_errors=True)
    assert text.startswith("S0") and "✓" in text and "tactic_failed" in text
    dot = tree_dot(result)
    assert dot.startswith("digraph") and "palegreen" in dot
