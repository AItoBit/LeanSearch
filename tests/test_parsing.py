from leansearch.parsing.errors import classify_error
from leansearch.parsing.normalize import normalize_goal, state_hash
from leansearch.parsing.state_parser import parse_goal
from leansearch.parsing.theorem_parser import (
    find_top_level_assign,
    local_definitions,
    parse_theorems,
    split_imports,
)
from leansearch.policy.prompt_builder import parse_tactics

SOURCE = """\
import Foo

open Nat

/-- helper -/
def f (n : Nat) : Nat := n + 1

theorem first (n : Nat) : f n = n + 1 := by
  rfl

/-- The second one. -/
theorem second {α : Type} (x : α) (h : (fun y : α => y) x = x := rfl) : x = x := by
  rfl

namespace Bar

example (a : Nat) : a = a := rfl

end Bar
"""


def test_parse_theorems_hides_proofs_and_other_theorems():
    thms = parse_theorems(SOURCE)
    assert [t.name for t in thms] == ["first", "second", "example_L17"]
    first, second, ex = thms
    assert first.signature == "theorem first (n : Nat) : f n = n + 1"
    assert first.reference_proof == "by\n  rfl"
    assert "def f" in first.context and "import Foo" in first.context
    assert "theorem" not in second.context
    assert second.signature.startswith("/-- The second one. -/\ntheorem second")
    assert second.signature.endswith(": x = x")
    assert "namespace Bar" in ex.context
    assert ex.is_example


def test_theorem_rendering():
    thm = parse_theorems(SOURCE)[0]
    assert thm.with_sorry().endswith(":= by sorry")
    assert thm.with_proof(["intro x", "cases x with\n| a => rfl"]) == (
        "theorem first (n : Nat) : f n = n + 1 := by\n  intro x\n  cases x with\n  | a => rfl"
    )
    ex = parse_theorems(SOURCE)[2]
    assert ex.checkable_signature("chk").startswith("theorem chk (a : Nat)")


def test_find_top_level_assign_skips_brackets_and_comments():
    text = "theorem t (h : x := 1) -- := no\n  : y := by simp"
    assert text[find_top_level_assign(text):].startswith(":= by simp")


def test_split_imports():
    imports, rest = split_imports("/- header\n-/\nimport A\n-- c\nimport B.C\n\nopen A\ndef x := 1")
    assert imports == "import A\nimport B.C"
    assert rest == "open A\ndef x := 1"
    assert split_imports("def x := 1") == ("", "def x := 1")


def test_local_definitions():
    assert local_definitions(SOURCE) == ["f"]


def test_normalize_renames_inaccessible_names():
    a = "n✝ : Nat\nh  :  n✝ > 0\n⊢ n✝ + 0 = n✝"
    b = "m✝¹ : Nat\nh : m✝¹ > 0\n⊢ m✝¹ + 0 = m✝¹"
    assert normalize_goal(a) == normalize_goal(b) == "_x0 : Nat\nh : _x0 > 0\n⊢ _x0 + 0 = _x0"
    assert state_hash([a]) == state_hash([b])
    assert state_hash([a]) != state_hash([a, a])
    assert state_hash([]) == "solved"


def test_parse_goal():
    g = parse_goal("case succ\na b : ℝ\nh : a ≤\n  b\n⊢ a + a ≤\n  b + b")
    assert g.case == "succ"
    assert [h.names for h in g.hypotheses] == [("a", "b"), ("h",)]
    assert g.hypotheses[1].type == "a ≤ b"
    assert g.target == "a + a ≤ b + b"


def test_classify_error():
    assert classify_error("unknown identifier 'foo'") == "unknown_identifier"
    assert classify_error("Type mismatch\n  h") == "type_mismatch"
    assert classify_error("<input>:1:1: unknown tactic") == "unknown_tactic"
    assert classify_error("simp made no progress") == "no_progress"
    assert classify_error("omega could not prove the goal") == "tactic_failed"
    assert classify_error("failed to synthesize\n  HAdd") == "typeclass_failure"
    assert classify_error("(deterministic) timeout at whnf") == "timeout"
    assert classify_error(None) is None


def test_parse_tactics_from_model_output():
    text = "Sure:\n```lean\n1. simp\n- exact add_le_add h h\ninduction n with\n  | zero => rfl\n-- note\n```"
    assert parse_tactics(text) == ["simp", "exact add_le_add h h", "induction n with\n  | zero => rfl"]
