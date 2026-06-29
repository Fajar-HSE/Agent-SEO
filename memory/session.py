"""SessionMemory — per-workflow in-memory store."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class SessionMemory:
    """Ephemeral memory — lives for one workflow run."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._history: list[dict[str, Any]] = []

    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Set key-value pair."""
        self._data[key] = value

    def update(self, data: dict[str, Any]):
        """Bulk update from dict."""
        self._data.update(data)

    def get_context(self, agent_name: str) -> dict[str, Any]:
        """Get relevant context for an agent — all data so far."""
        return dict(self._data)

    def add_history(self, entry: dict[str, Any]):
        """Record a step execution in history."""
        self._history.append(entry)

    def get_history(self) -> list[dict[str, Any]]:
        """Get full execution history."""
        return list(self._history)

    def to_dict(self) -> dict[str, Any]:
        """Serialize full session state."""
        return {
            "data": dict(self._data),
            "history": list(self._history),
        }

    def clear(self):
        """Reset session memory."""
        self._data.clear()
        self._history.clear()
