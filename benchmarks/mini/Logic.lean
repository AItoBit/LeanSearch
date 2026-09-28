/-
Micro benchmark: propositional and first-order logic (core Lean 4, no Mathlib).
-/

theorem and_swap' (p q : Prop) (h : p ∧ q) : q ∧ p := by
  exact ⟨h.2, h.1⟩

theorem or_swap' (p q : Prop) (h : p ∨ q) : q ∨ p := by
  cases h with
  | inl hp => exact Or.inr hp
  | inr hq => exact Or.inl hq

theorem imp_trans' (p q r : Prop) (hpq : p → q) (hqr : q → r) : p → r := by
  intro hp
  exact hqr (hpq hp)

theorem modus_ponens' (p q : Prop) (hp : p) (hpq : p → q) : q := by
  exact hpq hp

theorem and_imp_left (p q : Prop) : p ∧ q → p := by
  intro h
  exact h.1

theorem iff_refl' (p : Prop) : p ↔ p := by
  exact Iff.rfl

theorem not_not_intro' (p : Prop) (hp : p) : ¬¬p := by
  intro hn
  exact hn hp

theorem forall_and_left {α : Type} (P Q : α → Prop) (h : ∀ x, P x ∧ Q x) : ∀ x, P x := by
  intro x
  exact (h x).1

theorem exists_of_forall_nat (P : Nat → Prop) (h : ∀ n, P n) : ∃ n, P n := by
  exact ⟨0, h 0⟩

theorem and_or_distrib' (p q r : Prop) (h : p ∧ (q ∨ r)) : (p ∧ q) ∨ (p ∧ r) := by
  obtain ⟨hp, hq | hr⟩ := h
  · exact Or.inl ⟨hp, hq⟩
  · exact Or.inr ⟨hp, hr⟩

theorem bool_and_comm' (a b : Bool) : (a && b) = (b && a) := by
  cases a <;> cases b <;> rfl
