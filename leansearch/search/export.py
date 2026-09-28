"""Render search trees as text or Graphviz DOT."""

from __future__ import annotations

from leansearch.search.base import SearchResult
from leansearch.search.node import SearchNode, Status

_MARK = {Status.SOLVED: "✓", Status.FAILED: "✗", Status.PRUNED: "⊘", Status.OPEN: "…", Status.EXPANDED: ""}


def tree_text(result: SearchResult, show_errors: bool = False) -> str:
    if result.root is None:
        return "(empty tree)"
    failures: dict[int, list[str]] = {}
    if show_errors:
        by_state = {n.state: n.node_id for n in result.nodes}
        for t in result.transitions:
            if not t.ok and t.state in by_state:
                failures.setdefault(by_state[t.state], []).append(f"{t.action.tactic}  ✗ {t.error_kind}")

    lines = [f"S{result.root.node_id}"]

    def walk(node: SearchNode, prefix: str) -> None:
        items: list[tuple[str, SearchNode | None]] = [(_label(c), c) for c in node.children]
        items += [(f, None) for f in failures.get(node.node_id, [])]
        for i, (label, child) in enumerate(items):
            last = i == len(items) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{label}")
            if child is not None:
                walk(child, prefix + ("    " if last else "│   "))

    walk(result.root, "")
    return "\n".join(lines)


def _label(node: SearchNode) -> str:
    tactic = (node.action.tactic if node.action else "").replace("\n", " ⏎ ")
    mark = _MARK[node.status]
    note = f" ({node.note})" if node.note else ""
    return f"{tactic}  → S{node.node_id} {mark}{note}".rstrip()


def tree_dot(result: SearchResult) -> str:
    colors = {Status.SOLVED: "palegreen", Status.FAILED: "lightpink", Status.PRUNED: "lightgray",
              Status.OPEN: "lightyellow", Status.EXPANDED: "lightblue"}
    out = ["digraph search {", '  node [shape=box, style=filled, fontname="monospace"];']
    for n in result.nodes:
        goal = (n.state.parsed_goals[0].target if n.state.goals else "no goals")[:60]
        label = f"S{n.node_id} [{len(n.state.goals)} goals]\n{goal}"
        out.append(f"  n{n.node_id} [label={_quote(label)}, fillcolor={colors[n.status]}];")
        if n.parent is not None and n.action is not None:
            out.append(f"  n{n.parent.node_id} -> n{n.node_id} [label={_quote(n.action.tactic[:40])}];")
    out.append("}")
    return "\n".join(out)


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
