from __future__ import annotations

from leansearch.environment.proof_state import Action, ProofState
from leansearch.models.api import ChatClient
from leansearch.policy.base import PolicyContext, TacticPolicy, dedupe_actions, rank_logprobs
from leansearch.policy.prompt_builder import SYSTEM_PROMPT, build_tactic_prompt, parse_tactics


class LLMTacticPolicy(TacticPolicy):
    """Asks a chat model for a list of tactics in one completion; the rank order
    becomes the prior since chat APIs rarely expose per-tactic probabilities."""

    name = "llm"

    def __init__(self, client: ChatClient):
        super().__init__()
        self.client = client

    def propose(self, state: ProofState, n: int, context: PolicyContext | None = None) -> list[Action]:
        self.calls += 1
        completion = self.client.chat(SYSTEM_PROMPT, build_tactic_prompt(state, n, context))
        self.tokens_used += completion.prompt_tokens + completion.completion_tokens
        tactics = [t for text in completion.texts for t in parse_tactics(text)]
        actions = dedupe_actions([Action(t, source=f"llm:{self.client.model}") for t in tactics], n)
        return [Action(a.tactic, lp, a.source) for a, lp in zip(actions, rank_logprobs(len(actions)))]

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "model": self.client.model,
            "base_url": self.client.base_url,
            "temperature": self.client.temperature,
            "seed": self.client.seed,
        }
