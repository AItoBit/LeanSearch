import Mathlib

/-! Mathlib-dependent example problems for LeanSearch (proofs are hidden from the prover). -/

theorem real_double_le (a b : ℝ) (h : a ≤ b) : a + a ≤ b + b := by
  linarith

theorem real_sq_nonneg' (x : ℝ) : 0 ≤ x ^ 2 := by
  positivity

theorem real_add_sq' (a b : ℝ) : (a + b) ^ 2 = a ^ 2 + 2 * a * b + b ^ 2 := by
  ring

theorem set_inter_comm' {α : Type*} (s t : Set α) : s ∩ t = t ∩ s := by
  exact Set.inter_comm s t
