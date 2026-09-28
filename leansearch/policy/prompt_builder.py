"""Structured, sectioned prompts for tactic generation."""

from __future__ import annotations

import re

from leansearch.environment.proof_state import ProofState
from leansearch.policy.base import PolicyContext

SYSTEM_PROMPT = (
    "You are an expert Lean 4 and Mathlib user. You propose single tactic steps for a "
    "given proof state. Lean will check every tactic, so diversity matters more than "
    "confidence. Never use `sorry` or `admit`."
)


def build_tactic_prompt(state: ProofState, n: int, context: PolicyContext | None = None) -> str:
    context = context or PolicyContext()
    goal = state.parsed_goals[0] if state.goals else None
    sections: list[tuple[str, str]] = []
    if context.theorem:
        sections.append(("THEOREM", context.theorem))
    sections.append(("GOAL", f"⊢ {goal.target}" if goal else "no goals"))
    if goal and goal.hypotheses:
        sections.append(("LOCAL CONTEXT", "\n".join(str(h) for h in goal.hypotheses)))
    if len(state.goals) > 1:
        sections.append(("OTHER GOALS", "\n\n".join(state.goals[1:])))
    if context.premises:
        sections.append(("RELEVANT PREMISES", "\n".join(context.premises)))
    if context.previous_tactics:
        sections.append(("PREVIOUS TACTICS", "\n".join(context.previous_tactics)))
    if context.feedback:
        sections.append(("LEAN FEEDBACK", "\n\n".join(context.feedback)))
    sections.append(
        (
            "TASK",
            f"Propose {n} different Lean 4 tactics to run next on the first goal. "
            "Output exactly one tactic per line inside a single ```lean code block, "
            "with no numbering and no explanation. A tactic may span several lines only "
            "if later lines are indented.",
        )
    )
    return "\n\n".join(f"[{title}]\n{body}" for title, body in sections)


_FENCE = re.compile(r"```(?:lean4?|)\s*\n(.*?)```", re.S)
_NUMBERING = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+")


def parse_tactics(text: str) -> list[str]:
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    tactics: list[str] = []
    for line in body.splitlines():
        if not line.strip() or line.strip().startswith("--"):
            continue
        if line[:1].isspace() and tactics:
            tactics[-1] += "\n" + line.rstrip()
            continue
        tactic = _NUMBERING.sub("", line).strip().strip("`").strip()
        if tactic and tactic not in {"by", "lean"}:
            tactics.append(tactic)
    return tactics
