"""Stateful tactic-level interaction with Lean through the REPL."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from leansearch.environment.proof_state import Action, ProofState, Transition
from leansearch.environment.repl import LeanProcessError, ReplProcess, default_project_dir
from leansearch.parsing.errors import classify_error
from leansearch.parsing.theorem_parser import Theorem, split_imports

FORBIDDEN_TACTICS = re.compile(r"\b(sorry|admit)\b|\bnative_decide\b|\bdecide\s*\+\s*native")


class LeanSetupError(RuntimeError):
    """The theorem statement or its context does not elaborate."""


@dataclass
class LeanConfig:
    repl_path: str | None = None
    project_dir: str | None = None
    repl_mode: str | None = None
    start_timeout: float = 300.0
    tactic_timeout: float = 30.0
    max_heartbeats: int | None = 200_000


def base_command(imports: str, max_heartbeats: int | None) -> str:
    parts = [imports] if imports else []
    parts.append(f"set_option maxHeartbeats {max_heartbeats if max_heartbeats is not None else 200000}")
    return "\n\n".join(parts)


def error_messages(resp: dict[str, Any]) -> list[str]:
    return [m.get("data", "") for m in resp.get("messages", []) if m.get("severity") == "error"]


class LeanEnv:
    """Runs tactics on proof states of one theorem at a time.

    Every `ProofState` carries the tactic path from the root. If the REPL is
    restarted (timeout, crash), old handles become invalid and states are
    transparently rebuilt by replaying their paths.
    """

    def __init__(self, config: LeanConfig | None = None):
        self.config = config or LeanConfig()
        self.repl = ReplProcess(self.config.repl_path, self.config.project_dir, self.config.repl_mode)
        self.lean_calls = 0
        self.restarts = 0
        self._generation = 0
        self._env_cache: dict[str, int] = {}
        self._theorem: Theorem | None = None
        self._rebuilt: dict[tuple[str, ...], int] = {}

    # ------------------------------------------------------------------ setup

    def _restart(self) -> None:
        self.repl.close()
        self._generation += 1
        self.restarts += 1
        self._env_cache.clear()
        self._rebuilt.clear()

    def _send(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.lean_calls += 1
        try:
            return self.repl.send(payload, timeout)
        except LeanProcessError:
            self._restart()
            raise

    def _elaborate(self, cmd: str, env: int | None, what: str) -> int:
        payload: dict[str, Any] = {"cmd": cmd}
        if env is not None:
            payload["env"] = env
        resp = self._send(payload, self.config.start_timeout)
        if "message" in resp:
            raise LeanSetupError(resp["message"])
        errors = error_messages(resp)
        if errors:
            raise LeanSetupError(f"{what} failed to elaborate:\n" + "\n".join(errors))
        return resp["env"]

    def _context_env(self, context: str) -> int:
        """Environment for a theorem's context: a cached imports-only base
        environment, extended with the rest of the context."""
        if context in self._env_cache:
            return self._env_cache[context]
        imports, body = split_imports(context)
        base_key = "\0imports\0" + imports
        if base_key not in self._env_cache:
            self._env_cache[base_key] = self._elaborate(base_command(imports, self.config.max_heartbeats),
                                                        None, "imports")
        env = self._env_cache[base_key]
        if body:
            env = self._elaborate(body, env, "theorem context")
        self._env_cache[context] = env
        return env

    def _open_root(self, theorem: Theorem) -> ProofState:
        env = self._context_env(theorem.context)
        resp = self._send({"cmd": theorem.with_sorry(), "env": env}, self.config.start_timeout)
        if "message" in resp:
            raise LeanSetupError(resp["message"])
        errors = error_messages(resp)
        sorries = resp.get("sorries", [])
        if errors or len(sorries) != 1:
            detail = "\n".join(errors) or f"expected exactly one sorry, got {len(sorries)}"
            raise LeanSetupError(f"cannot open {theorem.name}: {detail}")
        s = sorries[0]
        return ProofState(goals=(s["goal"],), handle=s["proofState"], generation=self._generation)

    def start(self, theorem: Theorem) -> ProofState:
        self._theorem = theorem
        self._rebuilt.clear()
        try:
            return self._open_root(theorem)
        except LeanProcessError:
            return self._open_root(theorem)

    # -------------------------------------------------------------- execution

    def _handle(self, state: ProofState) -> int:
        if state.generation == self._generation:
            return state.handle
        if self._theorem is None:
            raise RuntimeError("no active theorem; call start() first")
        path = state.tactics
        k = next((k for k in range(len(path), -1, -1) if path[:k] in self._rebuilt), None)
        if k is None:
            self._rebuilt[()] = self._open_root(self._theorem).handle
            k = 0
        handle = self._rebuilt[path[:k]]
        for i in range(k, len(path)):
            resp = self._send({"tactic": path[i], "proofState": handle}, self.config.tactic_timeout)
            if "message" in resp or error_messages(resp):
                raise LeanProcessError(f"replay of {path[: i + 1]} diverged after restart")
            handle = resp["proofState"]
            self._rebuilt[path[: i + 1]] = handle
        return handle

    def run_tactic(self, state: ProofState, action: Action | str) -> Transition:
        if isinstance(action, str):
            action = Action(action, source="manual")
        tactic = action.tactic.strip()
        t0 = time.perf_counter()

        def fail(msg: str, kind: str | None = None) -> Transition:
            return Transition(state, action, None, msg, kind or classify_error(msg), (time.perf_counter() - t0) * 1000)

        if not tactic:
            return fail("empty tactic", "syntax_error")
        if FORBIDDEN_TACTICS.search(tactic):
            return fail(f"forbidden tactic: {tactic}", "forbidden")
        if state.solved:
            return fail("no goals to be proved", "no_progress")

        try:
            handle = self._handle(state)
            resp = self._send({"tactic": tactic, "proofState": handle}, self.config.tactic_timeout)
        except LeanProcessError as exc:
            return fail(str(exc), "timeout" if "within" in str(exc) else "process_error")

        if "message" in resp:
            return fail(resp["message"].removeprefix("Lean error:\n"))
        errors = error_messages(resp)
        if errors:
            return fail("\n".join(errors))
        if resp.get("sorries"):
            return fail("tactic introduced sorry", "forbidden")

        goals = tuple(resp.get("goals", []))
        status = resp.get("proofStatus", "Completed")
        if not goals and status != "Completed":
            return fail(f"goals closed but proof rejected: {status}", "elaboration_failure")

        new_state = ProofState(goals, state.tactics + (tactic,), resp["proofState"], self._generation)
        return Transition(state, action, new_state, None, None, (time.perf_counter() - t0) * 1000)

    def is_solved(self, state: ProofState) -> bool:
        return state.solved

    def close(self) -> None:
        self.repl.close()

    def __enter__(self) -> "LeanEnv":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def lean_toolchain(config: LeanConfig) -> str | None:
    path = Path(config.project_dir or default_project_dir()) / "lean-toolchain"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None
