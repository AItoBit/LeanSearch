"""Coarse taxonomy of Lean errors, used for statistics and error routing."""

from __future__ import annotations

import re

_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("timeout", re.compile(r"deterministic\)? timeout|maximum recursion depth|heartbeats|did not answer within", re.I)),
    ("forbidden", re.compile(r"forbidden tactic", re.I)),
    ("unknown_identifier", re.compile(r"unknown (identifier|constant)", re.I)),
    ("unknown_tactic", re.compile(r"unknown tactic", re.I)),
    ("syntax_error", re.compile(r"unexpected token|expected '|unexpected identifier|:\d+:\d+: expected", re.I)),
    ("typeclass_failure", re.compile(r"failed to synthesize", re.I)),
    ("type_mismatch", re.compile(r"type mismatch", re.I)),
    ("unsolved_goals", re.compile(r"unsolved goals", re.I)),
    ("no_progress", re.compile(r"made no progress|no goals to be proved|no progress", re.I)),
    ("tactic_failed", re.compile(r"failed|could not|did not|not applicable|unable to|abortTactic", re.I)),
]

ERROR_KINDS = [kind for kind, _ in _RULES] + ["elaboration_failure", "process_error"]


def classify_error(message: str | None) -> str | None:
    if message is None:
        return None
    for kind, pattern in _RULES:
        if pattern.search(message):
            return kind
    return "elaboration_failure"
