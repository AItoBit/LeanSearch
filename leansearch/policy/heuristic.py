"""A model-free tactic policy: automation tactics plus hypothesis-aware moves.

It is the reproducible zero-cost baseline, and lets the whole search stack be
exercised without any LLM.
"""

from __future__ import annotations

import re

from leansearch.environment.proof_state import Action, ProofState
from leansearch.policy.base import PolicyContext, TacticPolicy, dedupe_actions, rank_logprobs

CORE_AUTOMATION = [
    "rfl",
    "simp",
    "omega",
    "decide",
    "simp_all",
    "trivial",
    "assumption",
    "constructor",
    "simp [*]",
    "exact?",
]
MATHLIB_AUTOMATION = ["norm_num", "linarith", "ring", "positivity", "nlinarith", "aesop", "tauto"]

_INDUCTIVE_TYPE = re.compile(r"^(ℕ|Nat|List\b.*|Bool|Option\b.*|ℤ|Int)$")
_TYPE_UNIVERSE = re.compile(r"^(Prop|Type\S*|Sort\S*|.*→ (Prop|Type\S*|Sort\S*))$")


class HeuristicPolicy(TacticPolicy):
    name = "heuristic"

    def __init__(self, mathlib: bool = False, allow_exact_search: bool = False):
        super().__init__()
        self.mathlib = mathlib
        self.allow_exact_search = allow_exact_search

    def candidates(self, state: ProofState, definitions: list[str] | None = None) -> list[str]:
        """Ordered candidates: goal-shape moves, cheap closers, unfolding local
        definitions, hypothesis-driven moves, then the remaining automation."""
        if not state.goals:
            return []
        goal = state.parsed_goals[0]
        target = goal.target
        out: list[str] = []

        if target.startswith(("∀", "¬")) or _top_level_arrow(target):
            out += ["intro", "intros"]
        if target.startswith("∃"):
            out += ["constructor", "exact ⟨_, rfl⟩"]
        if "↔" in target:
            out.append("constructor")
        if "∧" in target:
            out.append("constructor")
        if "∨" in target:
            out += ["left", "right"]

        automation = list(CORE_AUTOMATION)
        if not self.allow_exact_search:
            automation.remove("exact?")
        closers, rest = automation[:4], automation[4:]
        if self.mathlib:
            closers += MATHLIB_AUTOMATION
        out += closers

        goal_text = state.goals[0]
        used = [d for d in definitions or [] if re.search(rf"(?<![\w.]){re.escape(d)}(?![\w'])", goal_text)]
        names = ", ".join(used)
        if used:
            out.append(f"simp [{names}]")

        structural: list[str] = []
        direct: list[str] = []
        for hyp in goal.hypotheses:
            if hyp.type == target:
                out += [f"exact {n}" for n in hyp.names if "✝" not in n]
            elif hyp.type.endswith(f"→ {target}"):
                out += [f"apply {n}" for n in hyp.names if "✝" not in n]
        for hyp in goal.hypotheses:
            if _TYPE_UNIVERSE.match(hyp.type):
                continue
            for name in hyp.names:
                if "✝" in name:
                    continue
                if _INDUCTIVE_TYPE.match(hyp.type):
                    structural += [f"induction {name}", f"cases {name}"]
                elif hyp.type.startswith(("∃", "∧")) or " ∧ " in hyp.type or " ∨ " in hyp.type:
                    structural.append(f"obtain ⟨_, _⟩ := {name}" if "∨" not in hyp.type else f"cases {name}")
                elif " = " in hyp.type:
                    direct += [f"rw [{name}]", f"simp [{name}]", f"exact {name}"]
                else:
                    direct += [f"exact {name}", f"apply {name}", f"simp [{name}]"]
        # Interleave so neither kind of move starves the other at small k.
        for i in range(max(len(structural), len(direct))):
            out += structural[i : i + 1] + direct[i : i + 1]
        if used:
            out += [f"simp_all [{names}]", f"simp [{names}, *]"]
        return out + rest

    def propose(self, state: ProofState, n: int, context: PolicyContext | None = None) -> list[Action]:
        self.calls += 1
        tactics = self.candidates(state, context.definitions if context else None)
        actions = dedupe_actions([Action(t, source=self.name) for t in tactics], n)
        return [Action(a.tactic, lp, a.source) for a, lp in zip(actions, rank_logprobs(len(actions)))]

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "mathlib": self.mathlib}


def _top_level_arrow(target: str) -> bool:
    depth = 0
    for i, c in enumerate(target):
        if c in "([{⟨":
            depth += 1
        elif c in ")]}⟩":
            depth -= 1
        elif c == "→" and depth == 0:
            return True
    return False
