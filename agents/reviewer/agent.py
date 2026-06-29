"""Reviewer agent — reviews and scores article quality."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class ReviewerAgent(BaseAgent):
    """Reviews content quality, accuracy, readability, SEO compliance."""

    prompt_name = "reviewer"

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
            "quality_score": parsed.get("quality_score", 0),
            "approved": parsed.get("approved", False),
            "feedback": parsed.get("feedback", ""),
            "issues": parsed.get("issues", []),
            "suggestions": parsed.get("suggestions", []),
        }
