"""Interfaces that decouple search/policy code from any concrete Lean backend."""

from __future__ import annotations

from typing import Protocol

from leansearch.environment.proof_state import Action, ProofState, Transition, VerificationResult
from leansearch.parsing.theorem_parser import Theorem


class ProofEnvironment(Protocol):
    lean_calls: int

    def start(self, theorem: Theorem) -> ProofState: ...

    def run_tactic(self, state: ProofState, action: Action | str) -> Transition: ...

    def close(self) -> None: ...


class ProofVerifier(Protocol):
    def verify(self, theorem: Theorem, tactics: list[str] | tuple[str, ...]) -> VerificationResult: ...
