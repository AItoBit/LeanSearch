/-
Micro benchmark: list identities (core Lean 4, no Mathlib).
-/

theorem list_append_nil' (l : List Nat) : l ++ [] = l := by
  simp

theorem list_nil_append' (l : List Nat) : [] ++ l = l := by
  rfl

theorem list_length_append' (l₁ l₂ : List Nat) : (l₁ ++ l₂).length = l₁.length + l₂.length := by
  simp

theorem list_reverse_reverse' (l : List Nat) : l.reverse.reverse = l := by
  simp

theorem list_map_id'' (l : List Nat) : l.map id = l := by
  simp

theorem list_length_map' (l : List Nat) (f : Nat → Nat) : (l.map f).length = l.length := by
  simp

theorem list_append_assoc' (a b c : List Nat) : a ++ b ++ c = a ++ (b ++ c) := by
  simp

theorem list_length_cons' (x : Nat) (l : List Nat) : (x :: l).length = l.length + 1 := by
  rfl

theorem list_concrete_reverse : [1, 2, 3].reverse = [3, 2, 1] := by
  decide

def double : List Nat → List Nat
  | [] => []
  | x :: xs => (2 * x) :: double xs

theorem double_length (l : List Nat) : (double l).length = l.length := by
  induction l with
  | nil => rfl
  | cons x xs ih => simp [double, ih]

theorem double_append (a b : List Nat) : double (a ++ b) = double a ++ double b := by
  induction a with
  | nil => rfl
  | cons x xs ih => simp [double, ih]

theorem double_eq_map (l : List Nat) : double l = l.map (2 * ·) := by
  induction l with
  | nil => rfl
  | cons x xs ih => simp [double, ih]
