"""Independent replay of a finished proof in a clean Lean environment."""

from __future__ import annotations

import re
import time

from leansearch.environment.lean_env import FORBIDDEN_TACTICS, LeanConfig, base_command, error_messages
from leansearch.environment.proof_state import VerificationResult
from leansearch.environment.repl import LeanProcessError, ReplProcess
from leansearch.parsing.theorem_parser import Theorem, split_imports

STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
_CHECK_NAME = "leansearch_check_example"
_USES_SORRY = re.compile(r"declaration uses .sorry.")


class Verifier:
    """Accepts a proof only if Lean compiles it as a complete declaration, starting
    from a fresh environment (never the search session's), with no errors, no
    `sorry`, and no axioms beyond Lean's standard three.

    The verifier owns a REPL process separate from the search environment. With
    `fresh_process=True` it additionally spawns a new process for every check.
    """

    def __init__(
        self,
        config: LeanConfig | None = None,
        allowed_axioms: set[str] | None = None,
        fresh_process: bool = False,
    ):
        self.config = config or LeanConfig()
        self.allowed_axioms = allowed_axioms if allowed_axioms is not None else STANDARD_AXIOMS
        self.fresh_process = fresh_process
        self._repl: ReplProcess | None = None
        self._bases: dict[str, int] = {}

    def _process(self) -> ReplProcess:
        if self._repl is None or not self._repl.alive:
            self._bases.clear()
        if self._repl is None:
            self._repl = ReplProcess(self.config.repl_path, self.config.project_dir, self.config.repl_mode)
        return self._repl

    def _base_env(self, repl: ReplProcess, imports: str) -> int:
        """Imports-only environment. REPL environments are immutable, so every
        check starting from it sees nothing but the imports."""
        if imports not in self._bases:
            resp = repl.send({"cmd": base_command(imports, self.config.max_heartbeats)}, self.config.start_timeout)
            errors = error_messages(resp) or ([resp["message"]] if "message" in resp else [])
            if errors:
                raise LeanProcessError("imports failed to elaborate:\n" + "\n".join(errors))
            self._bases[imports] = resp["env"]
        return self._bases[imports]

    def verify(self, theorem: Theorem, tactics: list[str] | tuple[str, ...]) -> VerificationResult:
        t0 = time.perf_counter()
        proof = theorem.with_proof(tactics)
        checked = theorem.with_proof(tactics, signature=theorem.checkable_signature(_CHECK_NAME))
        name = _CHECK_NAME if theorem.is_example else theorem.name

        def result(ok: bool, messages: list[str], axioms: list[str] | None = None) -> VerificationResult:
            return VerificationResult(ok, proof, messages, axioms or [], (time.perf_counter() - t0) * 1000)

        if any(FORBIDDEN_TACTICS.search(t) for t in tactics):
            return result(False, ["proof contains a forbidden tactic"])

        imports, body = split_imports(theorem.context)
        source = "\n\n".join(p for p in (body, checked, f"#print axioms {name}") if p.strip())
        repl = self._process()
        try:
            base = self._base_env(repl, imports)
            resp = repl.send({"cmd": source, "env": base}, self.config.start_timeout)
        except LeanProcessError as exc:
            self._bases.clear()
            return result(False, [str(exc)])
        finally:
            if self.fresh_process:
                self.close()

        if "message" in resp:
            return result(False, [resp["message"]])
        errors = error_messages(resp)
        if errors:
            return result(False, errors)
        if resp.get("sorries"):
            return result(False, ["proof contains sorry"])
        infos = [m.get("data", "") for m in resp.get("messages", [])]
        if any(_USES_SORRY.search(m) for m in infos):
            return result(False, ["declaration uses sorry"])

        axioms = _parse_axioms(infos)
        if axioms is None:
            return result(False, ["could not read `#print axioms` output", *infos])
        bad = [a for a in axioms if a not in self.allowed_axioms]
        if bad:
            return result(False, [f"disallowed axioms: {', '.join(bad)}"], axioms)
        return result(True, [], axioms)

    def close(self) -> None:
        if self._repl is not None:
            self._repl.close()
            self._repl = None


def _parse_axioms(messages: list[str]) -> list[str] | None:
    for m in messages:
        if "does not depend on any axioms" in m:
            return []
        match = re.search(r"depends on axioms: \[(.*?)\]", m, re.S)
        if match:
            return [a.strip() for a in match.group(1).split(",") if a.strip()]
    return None
