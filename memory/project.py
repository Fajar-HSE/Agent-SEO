"""ProjectMemory — persistent JSON-based storage for SOPs, rules, brand voice."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class ProjectMemory:
    """Persistent project-level memory — stored as JSON file."""

    def __init__(self, file_path: str = "config/project_memory.json"):
        self.file_path = file_path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self):
        """Load memory from file."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.info(f"Project memory loaded: {len(self._data)} entries")
            except (json.JSONDecodeError, IOError):
                self._data = {}
        else:
            self._data = {
                "brand_voice": {},
                "seo_rules": {},
                "sop": {},
                "prompts": {},
            }

    def _save(self):
        """Persist memory to file."""
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get value by key."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Set key-value pair and persist."""
        self._data[key] = value
        self._save()

    def get_brand_voice(self) -> dict[str, Any]:
        """Get brand voice configuration."""
        return self._data.get("brand_voice", {})

    def get_seo_rules(self) -> dict[str, Any]:
        """Get SEO rules."""
        return self._data.get("seo_rules", {})

    def get_sop(self) -> dict[str, Any]:
        """Get standard operating procedures."""
        return self._data.get("sop", {})

    def to_dict(self) -> dict[str, Any]:
        """Return full project memory."""
        return dict(self._data)
