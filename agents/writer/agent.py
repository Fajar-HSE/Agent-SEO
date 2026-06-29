"""Writer agent — generates full article content."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class WriterAgent(BaseAgent):
    """Writes full article based on outline, keywords, and context."""

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
            "title": parsed.get("title", ""),
            "content": parsed.get("content", parsed.get("raw_text", "")),
            "excerpt": parsed.get("excerpt", ""),
            "word_count": parsed.get("word_count", 0),
        }
