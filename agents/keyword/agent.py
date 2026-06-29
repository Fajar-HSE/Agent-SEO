"""Keyword agent — finds and ranks target keywords."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class KeywordAgent(BaseAgent):
    """Researches keywords, search volume estimates, and keyword clusters."""

    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        messages = self._build_messages(input_data)
        raw = await llm_func(
            messages=messages,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        parsed = self._parse_output(raw)
        return {
            "primary_keyword": parsed.get("primary_keyword", ""),
            "secondary_keywords": parsed.get("secondary_keywords", []),
            "keyword_clusters": parsed.get("keyword_clusters", []),
            "long_tail_keywords": parsed.get("long_tail_keywords", []),
            "search_intent": parsed.get("search_intent", "informational"),
        }
