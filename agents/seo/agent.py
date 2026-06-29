"""SEO agent — optimizes content for search engines."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class SEOAgent(BaseAgent):
    """Optimizes article: meta tags, keyword density, readability, structure."""

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
            "optimized_content": parsed.get("optimized_content", ""),
            "meta_title": parsed.get("meta_title", ""),
            "meta_description": parsed.get("meta_description", ""),
            "seo_score": parsed.get("seo_score", 0),
            "keyword_density": parsed.get("keyword_density", {}),
            "improvements": parsed.get("improvements", []),
        }
