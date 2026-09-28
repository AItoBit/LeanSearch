"""Low-level JSON bridge to the leanprover-community REPL process."""

from __future__ import annotations

import functools
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

_EOF = object()


class LeanProcessError(RuntimeError):
    """The Lean REPL process died, hung, or produced unparseable output."""


class LeanTimeout(LeanProcessError):
    pass


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = Path(__file__).resolve().parent / "ReplLauncher.lean"


def default_repl_path() -> Path:
    env = os.environ.get("LEANSEARCH_REPL")
    if env:
        return Path(env)
    exe = "repl.exe" if os.name == "nt" else "repl"
    return ROOT / "vendor" / "repl" / ".lake" / "build" / "bin" / exe


def default_project_dir() -> Path:
    env = os.environ.get("LEANSEARCH_LEAN_PROJECT")
    return Path(env) if env else ROOT / "vendor" / "repl"


@functools.lru_cache(maxsize=None)
def lake_environment(project_dir: str) -> tuple[tuple[str, str], ...]:
    """Environment variables `lake env` sets up for a project (LEAN_PATH, PATH, ...).

    Resolved once so REPL processes can be launched directly: a `lake env`
    wrapper would otherwise sit between us and the REPL, and killing it does
    not kill the REPL on Windows.
    """
    dump = "import json, os; print(json.dumps(dict(os.environ)))"
    out = subprocess.run(
        ["lake", "env", sys.executable, "-c", dump],
        cwd=project_dir, capture_output=True, text=True, encoding="utf-8", timeout=600,
    )
    if out.returncode != 0:
        raise LeanProcessError(f"`lake env` failed in {project_dir}:\n{out.stderr[-2000:]}")
    return tuple(sorted(json.loads(out.stdout.strip().splitlines()[-1]).items()))


class ReplProcess:
    """One REPL subprocess. Commands are JSON objects separated by blank lines.

    The REPL runs in the environment of the Lake project `project_dir`, whose
    dependencies (e.g. Mathlib) are then importable. That project must depend
    on `REPL` (vendor/repl trivially does).

    mode:
      "binary"   - run the compiled `repl` executable.
      "lean-run" - interpret `REPL.Main.main` via `lean --run`; slower startup and
                   tactics, but works where unsigned executables are blocked
                   (e.g. Windows Smart App Control).
      "auto"     - use "binary", switching to "lean-run" if the binary cannot be
                   launched or dies before answering its first command.
    """

    def __init__(
        self,
        repl_path: Path | str | None = None,
        project_dir: Path | str | None = None,
        mode: str | None = None,
    ):
        self.repl_path = Path(repl_path) if repl_path else default_repl_path()
        self.project_dir = Path(project_dir) if project_dir else default_project_dir()
        self.mode = mode or os.environ.get("LEANSEARCH_REPL_MODE", "auto")
        self._auto = self.mode == "auto"
        self._answered = 0
        self._proc: subprocess.Popen[str] | None = None
        self._out: queue.Queue[Any] = queue.Queue()
        self._stderr: list[str] = []

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _command(self, mode: str, env: dict[str, str]) -> list[str]:
        if mode == "lean-run":
            lean = shutil.which("lean", path=env.get("PATH")) or "lean"
            return [lean, "--run", str(LAUNCHER)]
        if not self.repl_path.exists():
            raise FileNotFoundError(
                f"Lean REPL binary not found at {self.repl_path}. "
                "Build it with `lake build` in vendor/repl or set LEANSEARCH_REPL."
            )
        return [str(self.repl_path)]

    def start(self) -> None:
        if self.mode == "auto":
            self.mode = "binary" if self.repl_path.exists() else "lean-run"
        env = dict(lake_environment(str(self.project_dir.resolve())))
        self._out = queue.Queue()
        self._stderr = []
        self._answered = 0
        try:
            self._popen(self._command(self.mode, env), env)
        except OSError:
            if not (self._auto and self.mode == "binary"):
                raise
            self.mode = "lean-run"
            self._popen(self._command(self.mode, env), env)

    def _popen(self, cmd: list[str], env: dict[str, str]) -> None:
        self._proc = subprocess.Popen(
            cmd,
            cwd=str(self.project_dir),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, args=(self._proc, self._out), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self._proc,), daemon=True).start()

    @staticmethod
    def _read_stdout(proc: subprocess.Popen[str], out: queue.Queue[Any]) -> None:
        buf: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.strip():
                buf.append(line)
                continue
            if buf:
                out.put("".join(buf))
                buf = []
        if buf:
            out.put("".join(buf))
        out.put(_EOF)

    def _read_stderr(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            self._stderr.append(line)
            del self._stderr[:-200]

    def send(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if not self.alive:
            self.start()
        assert self._proc is not None and self._proc.stdin is not None
        try:
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n\n")
            self._proc.stdin.flush()
        except OSError as exc:
            self.close()
            raise LeanProcessError(f"failed to write to Lean REPL: {exc}") from exc

        try:
            raw = self._out.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise LeanTimeout(f"Lean REPL did not answer within {timeout:.0f}s") from None
        if raw is _EOF:
            stderr = "".join(self._stderr[-20:])
            self.close()
            if self._auto and self.mode == "binary" and self._answered == 0:
                self.mode = "lean-run"
                return self.send(payload, timeout)
            raise LeanProcessError(f"Lean REPL exited unexpectedly. stderr:\n{stderr}")
        try:
            resp = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.close()
            raise LeanProcessError(f"unparseable REPL output: {raw[:500]!r}") from exc
        self._answered += 1
        return resp

    def close(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        if proc.poll() is None:
            proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass

    def __enter__(self) -> "ReplProcess":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
