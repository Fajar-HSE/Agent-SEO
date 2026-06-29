"""Retry — exponential backoff retry logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


async def retry_call(
    func: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Any:
    """Call func with retry and exponential backoff."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_error = e
            if attempt < max_retries:
                wait = delay * (backoff ** (attempt - 1))
                logger.warning(f"Attempt {attempt}/{max_retries} failed: {e}. Retrying in {wait:.1f}s...")
                await asyncio.sleep(wait)
            else:
                logger.error(f"All {max_retries} attempts failed: {e}")

    raise last_error
