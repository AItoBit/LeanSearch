/-
Micro benchmark: natural-number arithmetic (core Lean 4, no Mathlib).
Reference proofs are hidden from the prover; they only certify well-formedness.
-/

theorem nat_add_zero' (n : Nat) : n + 0 = n := by
  rfl

theorem nat_zero_add' (n : Nat) : 0 + n = n := by
  simp

theorem nat_add_comm' (a b : Nat) : a + b = b + a := by
  omega

theorem nat_add_assoc' (a b c : Nat) : a + b + c = a + (b + c) := by
  omega

theorem nat_double_le (a b : Nat) (h : a ≤ b) : a + a ≤ b + b := by
  omega

theorem nat_succ_pos' (n : Nat) : 0 < n + 1 := by
  omega

theorem nat_mul_one' (n : Nat) : n * 1 = n := by
  simp

theorem nat_two_mul' (n : Nat) : 2 * n = n + n := by
  omega

theorem nat_lt_trans' (a b c : Nat) (h₁ : a < b) (h₂ : b < c) : a < c := by
  omega

theorem nat_sub_self' (n : Nat) : n - n = 0 := by
  simp

theorem nat_mul_comm' (a b : Nat) : a * b = b * a := by
  exact Nat.mul_comm a b

theorem nat_left_distrib' (a b c : Nat) : a * (b + c) = a * b + a * c := by
  exact Nat.left_distrib a b c

theorem nat_ten_eq : 2 * 5 = 10 := by
  decide

theorem nat_max_self' (n : Nat) : max n n = n := by
  simp

theorem nat_pow_two (n : Nat) : n ^ 2 = n * n := by
  exact Nat.pow_two n

theorem nat_even_or_odd (n : Nat) : n % 2 = 0 ∨ n % 2 = 1 := by
  omega

theorem nat_exists_gt (n : Nat) : ∃ m, n < m := by
  exact ⟨n + 1, Nat.lt_succ_self n⟩

def sumTo : Nat → Nat
  | 0 => 0
  | n + 1 => (n + 1) + sumTo n

theorem sumTo_zero : sumTo 0 = 0 := by
  rfl

theorem sumTo_ge (n : Nat) : n ≤ sumTo n := by
  cases n with
  | zero => simp [sumTo]
  | succ n => simp [sumTo]

theorem sumTo_formula (n : Nat) : 2 * sumTo n = n * (n + 1) := by
  induction n with
  | zero => rfl
  | succ n ih =>
    simp only [sumTo]
    rw [Nat.mul_add, ih]
    simp only [Nat.add_mul, Nat.mul_add, Nat.mul_one, Nat.one_mul]
    omega
