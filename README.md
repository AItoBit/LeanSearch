# LeanSearch

**Search-based formal reasoning agent for Lean 4.**

LeanSearch treats theorem proving as search over Lean-verified proof states
rather than one-shot text generation. Every edge in the search tree is a tactic
that Lean actually executed, and a proof is only reported after an independent
replay in a clean Lean environment.

This repository is at **v0.1**: the Lean bridge, proof-state abstraction,
tactic policies, greedy / BFS / beam / best-first search with state
deduplication, trajectory logging, independent verification, and a benchmark
evaluator. Retrieval, repair, learned models and MCTS come next (see
[Roadmap](#roadmap)).

## Quickstart

Requirements: Python ≥ 3.10, [elan](https://github.com/leanprover/elan), git.

```bash
# 1. Lean REPL (pins the Lean toolchain, v4.34.0)
git clone --depth 1 --branch v4.34.0 https://github.com/leanprover-community/repl vendor/repl
cd vendor/repl && lake build && cd ../..

# 2. Python package
pip install -e ".[dev]"

# 3. Milestone 1: load a theorem, apply tactics, replay the proof
leansearch step benchmarks/mini/Logic.lean:and_imp_left "intro h" "exact h.1"

# 4. Search for a proof
leansearch prove benchmarks/mini/Lists.lean:double_append --tree -k 10

# 5. Evaluate a benchmark under a fixed budget
leansearch eval benchmarks/mini --search best_first -k 10 --max-nodes 50
```

`leansearch step` output:

```text
[and_imp_left] initial state (1.67s, repl=binary):
p q : Prop
⊢ p ∧ q → p

>>> intro h   (2 ms)
p q : Prop
h : p ∧ q
⊢ p

>>> exact h.1   (5 ms)
no goals

Independent replay in a fresh Lean process: VERIFIED (1.35s, axioms: none)
```

`leansearch prove ... --tree` output (abridged):

```text
S0
├── induction a  → S1
│   ├── rfl  → S5
│   │   └── simp_all [double]  → S39 ✓
│   ├── simp [double]  → S7 ⊘ (duplicate_of:5)
│   ...
PROOF FOUND (verified by independent replay)

theorem double_append (a b : List Nat) : double (a ++ b) = double a ++ double b := by
  induction a
  rfl
  simp_all [double]

Nodes expanded: 6   tree size: 40   Lean calls: 60
Depth: 3   duplicates pruned: 14   invalid tactic rate: 33%
```

### LLM policy

Any OpenAI-compatible endpoint works (OpenAI, vLLM, llama.cpp server, Ollama):

```bash
export OPENAI_API_KEY=...                        # or a dummy key for local servers
leansearch prove benchmarks/mini/NatArith.lean:sumTo_formula \
    --policy llm --model gpt-4o-mini              # --base-url http://localhost:8000/v1 for vLLM
```

The model is asked for `k` tactics in one structured prompt
(`[GOAL] [LOCAL CONTEXT] [RELEVANT PREMISES] [PREVIOUS TACTICS] [TASK]`); Lean
checks each. `--candidate-cache cache.json` stores proposals per normalized state
for cheap, deterministic reruns.

### Mathlib

`lean/` is a Lake project depending on Mathlib and the REPL at `v4.34.0`:

```bash
cd lean && lake exe cache get && lake build && cd ..
leansearch prove lean/LeanSearchProblems.lean:real_double_le --project lean --mathlib
```

(`--mathlib` makes the heuristic policy also try `linarith`, `norm_num`,
`ring`, `positivity`, `aesop`, ...) This path is set up but has not been
exercised yet in this repository (it needs a ~5 GB Mathlib cache).

### Python API

```python
from leansearch import LeanSearch, load_theorem

with LeanSearch(search="best_first", max_nodes=200, num_candidates=10) as prover:
    result = prover.prove("benchmarks/mini/Lists.lean:double_length")

result.solved, result.proof, result.stats["lean_calls"], result.transitions
```

## First results

Mini benchmark (43 core-Lean theorems: Nat arithmetic, lists, logic), model-free
heuristic policy, `k = 10` candidates per state, identical budget for every
method (50 expansions / 400 Lean calls / depth 12 / 60 s per theorem).
Reproduce with `python scripts/run_matrix.py benchmarks/mini`.

| Method | Solved | Lean calls (total) | Lean calls / solved | Expansions / solved | Avg proof length | Time (s) |
|---|---:|---:|---:|---:|---:|---:|
| Greedy | 37/43 | 564 | 8.8 | 1.41 | 1.41 | 6.4 |
| BFS | 38/43 | 1417 | 12.6 | 1.79 | 1.45 | 15.4 |
| Beam-4 | 37/43 | 1046 | 10.7 | 1.60 | 1.41 | 13.7 |
| Beam-8 | 38/43 | 1273 | 12.6 | 1.79 | 1.45 | 12.6 |
| Beam-16 | 38/43 | 1417 | 12.6 | 1.79 | 1.45 | 12.1 |
| Best-first | 38/43 | 1417 | 12.6 | 1.79 | 1.45 | 13.5 |

The heuristic policy is a zero-cost baseline, not a prover; the table
validates the pipeline rather than answering a research question. Two things
it shows:

- The benchmark is too shallow to separate search algorithms: most proofs are
  one tactic long. The only theorem search solves and greedy does not is
  `or_swap'` (`cases h; simp_all; simp_all`), where greedy commits to a
  dead-end branch. Deeper problems are needed before search comparisons mean
  much.
- The 5 remaining failures (`nat_mul_comm'`, `nat_left_distrib'`,
  `nat_pow_two`, `forall_and_left`, `sumTo_formula`) need a specific library
  lemma or a nonlinear induction step. That is where retrieval and an LLM
  policy come in.

## Architecture

```text
Theorem (.lean file → statement + context, proof hidden)
   │
   ▼
LeanEnv ── ReplProcess ── leanprover-community/repl (JSON over stdio)
   │         start(theorem) → ProofState
   │         run_tactic(state, tactic) → Transition (new state | classified error)
   ▼
Searcher (greedy | bfs | beam | best_first)
   │  expand(node): policy.propose(state, k) → run each in Lean →
   │  prune no-progress / cycles / duplicates (normalized-state hash) →
   │  score = Σ policy logprob + heuristic value
   ▼
Verifier: replay the full declaration from an imports-only environment,
          reject errors, `sorry`, and non-standard axioms (`#print axioms`)
   ▼
SearchResult → trajectory JSONL (every node and transition, successful or not)
```

| Module | Contents |
|---|---|
| `leansearch/environment/` | `ReplProcess` (subprocess + timeouts), `LeanEnv` (tactic execution, state rebuild after crashes), `Verifier`, core data structures (`ProofState`, `Action`, `Transition`) |
| `leansearch/parsing/` | Lean file → theorems, goal parser, state normalization + hashing, error taxonomy |
| `leansearch/policy/` | `TacticPolicy` interface, `HeuristicPolicy`, `LLMTacticPolicy`, prompt builder, `CachedPolicy` |
| `leansearch/search/` | budget, nodes, shared expansion logic, algorithms, text/DOT tree export |
| `leansearch/scoring/` | `HeuristicScorer` (slot for the learned value model) |
| `leansearch/experience/` | trajectory records and JSONL writer/reader |
| `leansearch/evaluation/` | benchmark runner, metrics, run metadata (git commit, Lean version, config, hardware) |
| `scripts/` | `run_matrix.py` (experiment matrix), `check_benchmarks.py` (benchmark well-formedness) |

### Design decisions

- **Lean backend.** The environment layer is written against a small
  protocol (`start`, `run_tactic`, `close`), with the
  [leanprover-community REPL](https://github.com/leanprover-community/repl) as
  the first backend: one Lean dependency, builds in about a minute, gives
  persistent proof-state handles so search can branch from any state, and
  reports a kernel-checked `proofStatus` when goals close. LeanDojo-v2 /
  Pantograph remain the natural choice for repository tracing and Mathlib
  dataset extraction and can be added as a second backend behind the same
  protocol.
- **Proofs are hidden, not just unused.** A theorem's context contains only
  non-theorem declarations preceding it, so other benchmark problems (and their
  proofs) are never visible.
- **Trust.** `sorry`, `admit` and `native_decide` are refused before reaching
  Lean; the verifier re-elaborates the whole declaration in an environment that
  contains only the imports and checks `#print axioms` against
  `propext`, `Classical.choice`, `Quot.sound`. `leansearch step` uses a
  brand-new process for its replay.
- **Robustness.** Every `ProofState` carries its tactic path from the root. If
  the REPL times out or crashes, `LeanEnv` restarts it and transparently
  rebuilds states on demand. Tested with 1000+ repeated interactions.
- **Windows.** Where Smart App Control blocks the locally built `repl.exe`,
  `ReplProcess` falls back to interpreting the REPL through the signed `lean`
  executable (`--repl-mode lean-run`; about 25 s startup, about 100 ms per
  tactic, against about 5 ms with the binary).
- **Budgets.** Expansions, Lean calls, depth, wall time and tokens are all
  enforced by one `BudgetTracker`, so comparisons are made at equal compute.
- **Autoimplicit.** Core Lean has `autoImplicit` on: a typo such as
  `undefined_thing` in a statement silently becomes a universally quantified
  variable. Benchmark statements should be checked
  (`scripts/check_benchmarks.py`) or use `set_option autoImplicit false`.

## Tests

```bash
pytest -q                     # unit tests (fake environment) + Lean integration tests
pytest -q -m "not slow"       # skip the 1000-interaction stress test
python scripts/check_benchmarks.py benchmarks/mini
```

## Roadmap

| Milestone | Status |
|---|---|
| M1 Lean ↔ Python interaction, replay | done |
| M2 state → K tactic candidates → Lean | done (heuristic + LLM policy) |
| M3 beam / best-first search + state deduplication | done |
| M4 premise retrieval (BM25 → dense → hybrid) over Mathlib | next |
| M5 direct vs repair vs retrieval vs search benchmark | next (needs M4 + direct/repair baselines) |
| Learned value model, trajectory-trained policy, MCTS, self-improvement | later |

A research project named *LeanSearch* already exists (premise retrieval), so a
more distinctive public name may be worth choosing before release.
