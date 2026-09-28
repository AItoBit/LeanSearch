"""Minimal OpenAI-compatible chat client (works with OpenAI, vLLM, llama.cpp, Ollama, ...)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class Completion:
    texts: list[str]
    prompt_tokens: int
    completion_tokens: int


class ChatClient:
    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        timeout: float = 120.0,
        seed: int | None = None,
        retries: int = 3,
    ):
        self.model = model
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.seed = seed
        self.retries = retries

    def chat(self, system: str, user: str, n: int = 1) -> Completion:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "n": n,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                retriable = not isinstance(exc, urllib.error.HTTPError) or exc.code in (429, 500, 502, 503, 504)
                if attempt == self.retries - 1 or not retriable:
                    raise
                time.sleep(2**attempt)
        usage = data.get("usage", {})
        return Completion(
            texts=[c["message"]["content"] or "" for c in data["choices"]],
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
