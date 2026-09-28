"""Parse Lean's pretty-printed goals into hypotheses and targets."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hypothesis:
    names: tuple[str, ...]
    type: str

    def __str__(self) -> str:
        return f"{' '.join(self.names)} : {self.type}"


@dataclass(frozen=True)
class Goal:
    case: str | None
    hypotheses: tuple[Hypothesis, ...]
    target: str

    @property
    def accessible_names(self) -> list[str]:
        return [n for h in self.hypotheses for n in h.names if "✝" not in n]


def parse_goal(text: str) -> Goal:
    case: str | None = None
    entries: list[str] = []
    target_lines: list[str] = []
    in_target = False
    for line in text.splitlines():
        if in_target:
            target_lines.append(line.strip())
        elif line.startswith("⊢"):
            in_target = True
            target_lines.append(line[1:].strip())
        elif line.startswith("case ") and not entries:
            case = line[5:].strip()
        elif line[:1].isspace() and entries:
            entries[-1] += " " + line.strip()
        elif line.strip():
            entries.append(line.strip())

    hyps = []
    for entry in entries:
        names, sep, typ = entry.partition(" : ")
        if sep:
            hyps.append(Hypothesis(tuple(names.split()), typ.strip()))
    return Goal(case=case, hypotheses=tuple(hyps), target=" ".join(target_lines))
