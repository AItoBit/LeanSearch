"""Split a Lean source file into benchmark theorems and the context they live in.

Every `theorem` / `lemma` / `example` becomes a `Theorem` whose original proof
is hidden. Its context is every *non-theorem* top-level chunk preceding it
(imports, `open`, `namespace`, `def`s, ...), so other benchmark problems are
never visible as usable lemmas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DECL_START = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?"
    r"(?:(?:private|protected|noncomputable|partial|unsafe|nonrec)\s+)*"
    r"(?P<kw>theorem|lemma|example|def|abbrev|instance|structure|inductive|class|axiom|opaque"
    r"|open|namespace|end|section|variable|universe|import|set_option|attribute|notation"
    r"|infix|infixl|infixr|prefix|postfix|macro|syntax|macro_rules|elab|mutual|#\w+)\b"
)
_COMMENT_START = re.compile(r"^/-")
_THEOREM_KW = {"theorem", "lemma", "example"}
_OPEN = "([{⟨⦃"
_CLOSE = ")]}⟩⦄"


@dataclass(frozen=True)
class Theorem:
    name: str
    signature: str
    context: str = ""
    source: str | None = None
    line: int = 0
    reference_proof: str | None = None

    @property
    def is_example(self) -> bool:
        return self.decl_keyword == "example"

    @property
    def decl_keyword(self) -> str:
        m = _DECL_START.match(_strip_docstring(self.signature))
        return m.group("kw") if m else "theorem"

    def with_sorry(self) -> str:
        return f"{self.signature} := by sorry"

    def with_proof(self, tactics: list[str] | tuple[str, ...], signature: str | None = None) -> str:
        body = "\n".join(_indent(t) for t in tactics) if tactics else "  skip"
        return f"{signature or self.signature} := by\n{body}"

    def checkable_signature(self, check_name: str) -> str:
        """Signature with `example` turned into a named theorem so axioms can be audited."""
        if not self.is_example:
            return self.signature
        return re.sub(r"\bexample\b", f"theorem {check_name}", self.signature, count=1)


def _indent(tactic: str) -> str:
    return "\n".join("  " + line for line in tactic.splitlines())


def _strip_docstring(text: str) -> str:
    text = text.lstrip()
    if text.startswith("/-"):
        end = text.find("-/")
        if end != -1:
            return text[end + 2 :].lstrip()
    return text


def find_top_level_assign(text: str) -> int:
    """Index of the first `:=` outside brackets, strings and comments, or -1."""
    depth = 0
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            nl = text.find("\n", i)
            i = n if nl == -1 else nl
            continue
        if text.startswith("/-", i):
            end = text.find("-/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            depth = max(0, depth - 1)
        elif depth == 0 and text.startswith(":=", i):
            return i
        i += 1
    return -1


def _split_chunks(source: str) -> list[tuple[int, str, str]]:
    """Return (start_line, kind, text) chunks; kind is the declaration keyword or 'comment'."""
    chunks: list[tuple[int, str, list[str]]] = []
    in_block_comment = 0
    for lineno, line in enumerate(source.splitlines(), start=1):
        if in_block_comment == 0 and line and not line[0].isspace():
            m = _DECL_START.match(line)
            if m:
                chunks.append((lineno, m.group("kw"), [line]))
                in_block_comment += line.count("/-") - line.count("-/")
                continue
            if _COMMENT_START.match(line):
                chunks.append((lineno, "comment", [line]))
                in_block_comment += line.count("/-") - line.count("-/")
                continue
        in_block_comment = max(0, in_block_comment + line.count("/-") - line.count("-/"))
        if chunks:
            chunks[-1][2].append(line)
        else:
            chunks.append((lineno, "comment", [line]))
    return [(ln, kind, "\n".join(lines)) for ln, kind, lines in chunks]


def parse_theorems(source: str, source_name: str | None = None) -> list[Theorem]:
    theorems: list[Theorem] = []
    context: list[str] = []
    pending_doc: tuple[int, str] | None = None

    for lineno, kind, text in _split_chunks(source):
        if kind == "comment":
            if pending_doc is not None:
                context.append(pending_doc[1])
            pending_doc = (lineno, text) if text.lstrip().startswith("/--") else None
            if pending_doc is None:
                context.append(text)
            continue

        if kind in _THEOREM_KW:
            idx = find_top_level_assign(text)
            if idx == -1:
                raise ValueError(f"{source_name}:{lineno}: cannot find ':=' in declaration")
            signature = text[:idx].rstrip()
            start_line = lineno
            if pending_doc is not None:
                signature = pending_doc[1].rstrip() + "\n" + signature
                start_line = pending_doc[0]
                pending_doc = None
            if kind == "example":
                name = f"example_L{lineno}"
            else:
                m = re.search(rf"\b{kind}\s+([^\s(\[{{:⦃]+)", text)
                name = m.group(1) if m else f"{kind}_L{lineno}"
            theorems.append(
                Theorem(
                    name=name,
                    signature=signature,
                    context="\n".join(context).strip(),
                    source=source_name,
                    line=start_line,
                    reference_proof=text[idx + 2 :].strip(),
                )
            )
            continue

        if pending_doc is not None:
            context.append(pending_doc[1])
            pending_doc = None
        context.append(text)

    return theorems


def split_imports(context: str) -> tuple[str, str]:
    """Split a context into its leading `import` block and the rest.

    Lean only allows imports at the very start, so the import block can be
    elaborated once and shared as an immutable base environment.
    """
    lines = context.splitlines()
    imports: list[str] = []
    i = 0
    in_comment = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if in_comment or stripped.startswith("/-"):
            in_comment += line.count("/-") - line.count("-/")
            in_comment = max(in_comment, 0)
        elif stripped.startswith("import "):
            imports.append(stripped)
        elif stripped and not stripped.startswith("--"):
            break
        i += 1
    return "\n".join(imports), "\n".join(lines[i:]).strip()


_LOCAL_DEF = re.compile(r"^(?:@\[[^\]]*\]\s*)?(?:(?:private|protected|noncomputable)\s+)*(?:def|abbrev)\s+([^\s(\[{:]+)", re.M)


def local_definitions(context: str) -> list[str]:
    """Names of `def`/`abbrev`s declared in a theorem's context."""
    return _LOCAL_DEF.findall(context)


def load_theorems(path: str | Path) -> list[Theorem]:
    path = Path(path)
    return parse_theorems(path.read_text(encoding="utf-8"), source_name=str(path))


def load_theorem(spec: str) -> Theorem:
    """Load `path/to/File.lean:theorem_name`."""
    path, sep, name = spec.rpartition(":")
    if not sep or not path or len(path) == 1:
        raise ValueError(f"expected FILE.lean:NAME, got {spec!r}")
    theorems = load_theorems(path)
    for thm in theorems:
        if thm.name == name or thm.name.split(".")[-1] == name:
            return thm
    available = ", ".join(t.name for t in theorems)
    raise KeyError(f"theorem {name!r} not found in {path}. Available: {available}")
