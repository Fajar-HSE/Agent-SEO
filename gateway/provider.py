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

    def _get_api_key(self) -> str:
        """Get API key from environment variable."""
        if self.api_key_env:
            key = os.environ.get(self.api_key_env, "")
            if not key:
                raise ValueError(f"Missing env var: {self.api_key_env}")
            return key
        return ""

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
    """HuggingFace Inference API — free tier friendly."""

    name = "huggingface"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self.base_url = self.base_url or "https://api-inference.huggingface.co/models"

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        model = model or self.default_model or "Qwen/Qwen2.5-72B-Instruct"
        api_key = self._get_api_key()
        url = f"{self.base_url}/{model}"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        # Convert messages to prompt format
        prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "max_new_tokens": max_tokens,
                "return_full_text": False,
            },
        }
        data = await self._post(url, payload, headers)

        if isinstance(data, list) and data:
            return data[0].get("generated_text", "")
        return str(data)


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
        return data.get("message", {}).get("content", "")
