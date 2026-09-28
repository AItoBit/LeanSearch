"""High-level entry point: `LeanSearch(...).prove(theorem)`."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from leansearch.environment.lean_env import LeanConfig, LeanEnv
from leansearch.environment.verifier import Verifier
from leansearch.parsing.theorem_parser import Theorem, load_theorem
from leansearch.policy.base import TacticPolicy
from leansearch.policy.cache import CachedPolicy
from leansearch.policy.heuristic import HeuristicPolicy
from leansearch.search.algorithms import ALGORITHMS, BeamSearch
from leansearch.search.base import Searcher, SearchResult
from leansearch.search.budget import SearchBudget


@dataclass
class ProverConfig:
    search: str = "beam"
    beam_width: int = 8
    num_candidates: int = 8
    budget: SearchBudget = field(default_factory=SearchBudget)
    policy: str = "heuristic"
    mathlib: bool = False
    model: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    seed: int | None = 42
    candidate_cache: str | None = None
    verify: bool = True
    lean: LeanConfig = field(default_factory=LeanConfig)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_policy(config: ProverConfig) -> TacticPolicy:
    policy: TacticPolicy
    if config.policy == "heuristic":
        policy = HeuristicPolicy(mathlib=config.mathlib)
    elif config.policy == "llm":
        from leansearch.models.api import ChatClient
        from leansearch.policy.llm import LLMTacticPolicy

        if not config.model:
            raise ValueError("policy 'llm' requires --model")
        client = ChatClient(config.model, config.base_url, temperature=config.temperature, seed=config.seed)
        policy = LLMTacticPolicy(client)
    else:
        raise ValueError(f"unknown policy {config.policy!r}")
    if config.candidate_cache:
        policy = CachedPolicy(policy, config.candidate_cache)
    return policy


class LeanSearch:
    def __init__(self, config: ProverConfig | None = None, policy: TacticPolicy | None = None, **overrides):
        config = config or ProverConfig()
        for key, value in overrides.items():
            if hasattr(config.budget, key):
                config.budget = SearchBudget(**{**asdict(config.budget), key: value})
            elif hasattr(config, key):
                setattr(config, key, value)
            else:
                raise TypeError(f"unknown option {key!r}")
        if config.search not in ALGORITHMS:
            raise ValueError(f"unknown search {config.search!r}; choose from {sorted(ALGORITHMS)}")
        self.config = config
        self.env = LeanEnv(config.lean)
        self.verifier = Verifier(config.lean) if config.verify else None
        self.policy = policy or build_policy(config)
        self.searcher = self._build_searcher()

    def _build_searcher(self) -> Searcher:
        cls = ALGORITHMS[self.config.search]
        kwargs: dict[str, object] = {}
        if cls is BeamSearch:
            kwargs["beam_width"] = self.config.beam_width
        return cls(self.env, self.policy, self.verifier, self.config.budget, self.config.num_candidates, **kwargs)

    def prove(self, theorem: Theorem | str) -> SearchResult:
        if isinstance(theorem, str):
            theorem = load_theorem(theorem)
        return self.searcher.search(theorem)

    def close(self) -> None:
        if isinstance(self.policy, CachedPolicy):
            self.policy.save()
        self.env.close()
        if self.verifier is not None:
            self.verifier.close()

    def __enter__(self) -> "LeanSearch":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
