"""Research agent — collects context and supporting data."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class ResearchAgent(BaseAgent):
    """Researches topic context, trends, and supporting information."""

    prompt_name = "research"

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
            "context": parsed.get("context", ""),
            "trends": parsed.get("trends", []),
            "sources": parsed.get("sources", []),
            "key_facts": parsed.get("key_facts", []),
        }
