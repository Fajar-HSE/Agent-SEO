"""Publisher agent — publishes approved content to WordPress."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class PublisherAgent(BaseAgent):
    """Publishes article to WordPress via REST API."""

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        # Publisher doesn't need LLM — handles API calls directly
        title = input_data.get("title", "")
        content = input_data.get("content", "")
        status = input_data.get("publish_status", "draft")

        # TODO: WordPress REST API integration (Phase 3)
        return {
            "published": True,
            "post_id": 0,
            "url": "",
            "status": status,
            "message": f"Article '{title}' queued for publishing as {status}",
        }
