"""Canonical proof-state text, used for hashing, deduplication and caching."""

from __future__ import annotations

import hashlib
import re

# Inaccessible names such as `n✝`, `a✝¹`, `x✝²³`.
_INACCESSIBLE = re.compile(r"[^\s():,\[\]{}⟨⟩]+✝[⁰¹²³⁴⁵⁶⁷⁸⁹]*")
_WS = re.compile(r"[ \t]+")


def normalize_goal(goal: str) -> str:
    renames: dict[str, str] = {}

    def rename(m: re.Match[str]) -> str:
        return renames.setdefault(m.group(0), f"_x{len(renames)}")

    text = _INACCESSIBLE.sub(rename, goal)
    lines = [_WS.sub(" ", line).rstrip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def normalize_goals(goals: list[str] | tuple[str, ...]) -> str:
    return "\n<GOAL>\n".join(normalize_goal(g) for g in goals)


def state_hash(goals: list[str] | tuple[str, ...]) -> str:
    if not goals:
        return "solved"
    return hashlib.sha256(normalize_goals(goals).encode("utf-8")).hexdigest()[:16]
