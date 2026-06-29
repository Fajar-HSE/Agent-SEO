"""Provider — LLM provider abstraction."""

from __future__ import annotations

import os
import time
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .logger import log_request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token / cost tracking helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


# Per-model cost table (USD per 1k tokens).
# Kept minimal — add more models as needed.
_COST_PER_1K: dict[str, dict[str, float]] = {
    # OpenRouter
    "meta-llama/llama-3.1-70b-instruct": {"prompt": 0.001, "completion": 0.001},
    "google/gemini-flash-1.5": {"prompt": 0.000075, "completion": 0.0003},
    "mistralai/mistral-7b-instruct": {"prompt": 0.00007, "completion": 0.00007},
    # HuggingFace (free tier → 0 cost)
    "Qwen/Qwen2.5-72B-Instruct": {"prompt": 0.0, "completion": 0.0},
    # Ollama (local → 0 cost)
    "llama3.1:8b": {"prompt": 0.0, "completion": 0.0},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return estimated USD cost for a request."""
    rates = _COST_PER_1K.get(model, {"prompt": 0.0, "completion": 0.0})
    cost = (prompt_tokens / 1000) * rates["prompt"] + (completion_tokens / 1000) * rates["completion"]
    return round(cost, 6)


class Provider(ABC):
    """Base class for all LLM providers."""

    name: str = "base"

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.base_url = config.get("base_url", "")
        self.api_key_env = config.get("api_key_env", "")
        self.timeout = config.get("timeout", 60.0)
        self.models = config.get("models", {})
        self.default_model = config.get("default_model", "")
        # Token & cost accumulators (reset per session if needed)
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def _get_api_key(self) -> str:
        """Get API key from environment variable."""
        if self.api_key_env:
            key = os.environ.get(self.api_key_env, "")
            if not key:
                raise ValueError(f"Missing env var: {self.api_key_env}")
            return key
        return ""

    def _track_usage(self, model: str, prompt_text: str, completion_text: str):
        """Track token usage and estimate cost."""
        pt = _estimate_tokens(prompt_text)
        ct = _estimate_tokens(completion_text)
        self.total_tokens += pt + ct
        self.total_cost_usd += estimate_cost(model, pt, ct)
        logger.debug(
            f"[{self.name}] tokens: +{pt+ct} (total={self.total_tokens}), "
            f"cost: +${estimate_cost(model, pt, ct):.6f} (total=${self.total_cost_usd:.6f})"
        )

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Send completion request, return raw text response."""
        ...

    async def _post(self, url: str, payload: dict, headers: dict | None = None) -> dict:
        """HTTP POST with timeout and logging."""
        start = time.time()
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers or {})
            elapsed = (time.time() - start) * 1000
            log_request(self.name, url, resp.status_code, elapsed)
            resp.raise_for_status()
            return resp.json()


class HuggingFaceProvider(Provider):
    """
    HuggingFace Router — OpenAI-compatible endpoint via router.huggingface.co.
    Supports 100+ models with free tier access.
    """

    name = "huggingface"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        # Use the new router endpoint (OpenAI-compatible)
        self.base_url = "https://router.huggingface.co/v1"

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        model = model or self.default_model or "meta-llama/Llama-3.1-8B-Instruct"
        api_key = self._get_api_key()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        data = await self._post(url, payload, headers)

        choices = data.get("choices", [])
        text = ""
        if choices:
            text = choices[0].get("message", {}).get("content") or ""

        # Track usage (use actual tokens if available)
        usage = data.get("usage", {})
        pt = usage.get("prompt_tokens", _estimate_tokens("\n".join(m["content"] for m in messages)))
        ct = usage.get("completion_tokens", _estimate_tokens(text))
        self.total_tokens += pt + ct
        self.total_cost_usd += estimate_cost(model, pt, ct)

        return text


class OllamaProvider(Provider):
    """Ollama local LLM — unlimited, no API key needed."""

    name = "ollama"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.base_url = self.base_url or "http://localhost:11434"

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        model = model or self.default_model or "llama3.1:8b"
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        data = await self._post(url, payload)
        text = data.get("message", {}).get("content", "")
        prompt_text = "\n".join(m["content"] for m in messages)
        self._track_usage(model, prompt_text, text)
        return text


class OpenRouterProvider(Provider):
    """OpenRouter — multi-model gateway, supports free and paid models."""

    name = "openrouter"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.base_url = self.base_url or "https://openrouter.ai/api/v1"
        self.site_url = config.get("site_url", "")
        self.site_name = config.get("site_name", "SEO Agent")

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        model = model or self.default_model or "meta-llama/llama-3.1-70b-instruct:free"
        api_key = self._get_api_key()
        url = f"{self.base_url}/chat/completions"

        headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if self.site_url:
            headers["HTTP-Referer"] = self.site_url
        if self.site_name:
            headers["X-Title"] = self.site_name

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        data = await self._post(url, payload, headers)
        choices = data.get("choices", [])
        if not choices:
            return ""

        text = choices[0].get("message", {}).get("content", "")

        # Use actual token counts from response if available
        usage = data.get("usage", {})
        pt = usage.get("prompt_tokens", _estimate_tokens("\n".join(m["content"] for m in messages)))
        ct = usage.get("completion_tokens", _estimate_tokens(text))
        self.total_tokens += pt + ct
        self.total_cost_usd += estimate_cost(model, pt, ct)

        return text
