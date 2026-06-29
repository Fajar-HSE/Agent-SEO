"""Router — selects provider, handles fallback."""

from __future__ import annotations

import logging
from typing import Any

from .provider import Provider, HuggingFaceProvider, OllamaProvider
from .retry import retry_call
from .limiter import RateLimiter
from .cache import Cache

logger = logging.getLogger(__name__)

# Provider registry
PROVIDERS: dict[str, type[Provider]] = {
    "huggingface": HuggingFaceProvider,
    "ollama": OllamaProvider,
}


class Router:
    """Routes LLM requests to providers with fallback."""

    def __init__(self, config: dict[str, Any]):
        self.providers: dict[str, Provider] = {}
        self.fallback_order: list[str] = config.get("fallback_order", ["ollama"])
        self.cache = Cache(config.get("cache", {}))
        self.limiter = RateLimiter(config.get("rate_limit", {}))
        self._init_providers(config.get("providers", {}))

    def _init_providers(self, providers_config: dict[str, Any]):
        """Initialize configured providers."""
        for name, pconfig in providers_config.items():
            if name in PROVIDERS:
                self.providers[name] = PROVIDERS[name](pconfig)
                logger.info(f"Provider registered: {name}")

    def get_provider(self, name: str) -> Provider:
        """Get provider by name."""
        if name not in self.providers:
            raise ValueError(f"Unknown provider: {name}. Available: {list(self.providers.keys())}")
        return self.providers[name]

    async def complete(
        self,
        messages: list[dict[str, str]],
        model: str = "",
        provider: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Route completion request — try primary, fallback on failure."""
        # Check cache first
        cache_key = self.cache.make_key(messages, model)
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("Cache hit")
            return cached

        # Rate limit
        await self.limiter.acquire()

        # Build provider chain: specified first, then fallbacks
        chain = []
        if provider and provider in self.providers:
            chain.append(provider)
        for fb in self.fallback_order:
            if fb not in chain and fb in self.providers:
                chain.append(fb)

        if not chain:
            raise ValueError("No providers available")

        last_error = None
        for prov_name in chain:
            prov = self.providers[prov_name]
            try:
                result = await retry_call(
                    func=lambda m=messages, p=prov, mod=model, t=temperature, mt=max_tokens: p.complete(
                        messages=m, model=mod, temperature=t, max_tokens=mt
                    ),
                    max_retries=3,
                    delay=1.0,
                )
                self.cache.set(cache_key, result)
                return result
            except Exception as e:
                last_error = e
                logger.warning(f"Provider {prov_name} failed: {e}")
                continue

        raise RuntimeError(f"All providers failed. Last error: {last_error}")
