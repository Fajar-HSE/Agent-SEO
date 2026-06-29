"""Limiter — rate limiting for LLM API calls."""

from __future__ import annotations

import asyncio
import time
from typing import Any


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.rpm = config.get("rpm", 60)  # requests per minute
        self.interval = 60.0 / self.rpm
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait if needed to respect rate limit."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self._last_request = time.time()
