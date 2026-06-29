"""LongTermMemory — persists workflow outcomes across sessions."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    Stores summarized outcomes of past workflow runs.

    Each entry records:
    - workflow_id, workflow_name, keyword
    - quality_score, confidence, published status
    - learnings (reviewer feedback, suggestions)
    - timestamp

    Used to inform future runs with historical context.
    Storage: JSON file (future: vector DB / SQLite).
    """

    DEFAULT_FILE = "config/longterm_memory.json"
    MAX_ENTRIES = 500  # Trim oldest beyond this limit

    def __init__(self, file_path: str = DEFAULT_FILE):
        self.file_path = file_path
        self._entries: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        """Load memory from JSON file."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data if isinstance(data, list) else []
                logger.info(f"Long-term memory loaded: {len(self._entries)} entries")
            except (json.JSONDecodeError, IOError):
                self._entries = []
        else:
            self._entries = []

    def _save(self):
        """Persist memory to JSON file."""
        os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def record_workflow(
        self,
        workflow_id: str,
        workflow_name: str,
        keyword: str,
        quality_score: float = 0.0,
        avg_confidence: float = 0.0,
        published: bool = False,
        learnings: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Record a completed workflow outcome."""
        entry: dict[str, Any] = {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "keyword": keyword,
            "quality_score": quality_score,
            "avg_confidence": avg_confidence,
            "published": published,
            "learnings": learnings or [],
            "timestamp": time.time(),
        }
        if metadata:
            entry["metadata"] = metadata

        self._entries.append(entry)

        # Trim if over limit
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]

        self._save()
        logger.info(f"Long-term memory: recorded workflow {workflow_id}")

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_similar(self, keyword: str, top_k: int = 3) -> list[dict[str, Any]]:
        """
        Find past workflows with similar keywords.
        Simple substring match — replace with semantic search later.
        """
        kw_lower = keyword.lower()
        matches = [
            e for e in self._entries
            if kw_lower in e.get("keyword", "").lower()
            or e.get("keyword", "").lower() in kw_lower
        ]
        # Sort by most recent
        matches.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
        return matches[:top_k]

    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        """Return n most recent workflow records."""
        return sorted(self._entries, key=lambda e: e.get("timestamp", 0), reverse=True)[:n]

    def get_avg_quality(self) -> float:
        """Return average quality score across all recorded runs."""
        scores = [e["quality_score"] for e in self._entries if "quality_score" in e]
        return sum(scores) / len(scores) if scores else 0.0

    def get_learnings_for(self, keyword: str) -> list[str]:
        """Get aggregated learnings from past runs for similar keywords."""
        similar = self.get_similar(keyword)
        learnings: list[str] = []
        for entry in similar:
            learnings.extend(entry.get("learnings", []))
        return list(dict.fromkeys(learnings))  # deduplicate while preserving order

    def total_entries(self) -> int:
        return len(self._entries)
