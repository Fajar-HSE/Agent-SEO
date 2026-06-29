"""Cache — simple file-based caching for LLM responses."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class Cache:
    """File-based cache for LLM responses."""

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.ttl_seconds = config.get("ttl_seconds", 3600)  # 1 hour default
        self.cache_dir = config.get("cache_dir", "cache")

        if self.enabled:
            os.makedirs(self.cache_dir, exist_ok=True)

    def make_key(self, messages: list[dict], model: str) -> str:
        """Generate cache key from messages + model."""
        content = json.dumps({"messages": messages, "model": model}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, key: str) -> str | None:
        """Get cached response if valid."""
        if not self.enabled:
            return None

        path = os.path.join(self.cache_dir, f"{key}.json")
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - data.get("timestamp", 0) > self.ttl_seconds:
                os.remove(path)
                return None
            logger.debug(f"Cache hit: {key}")
            return data.get("response", "")
        except (json.JSONDecodeError, KeyError):
            return None

    def set(self, key: str, response: str):
        """Cache a response."""
        if not self.enabled:
            return

        path = os.path.join(self.cache_dir, f"{key}.json")
        data = {"response": response, "timestamp": time.time()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def clear(self):
        """Clear all cached responses."""
        if not os.path.exists(self.cache_dir):
            return
        for fname in os.listdir(self.cache_dir):
            if fname.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, fname))
        logger.info("Cache cleared")
