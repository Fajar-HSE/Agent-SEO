"""Planner agent — breaks task into structured outline."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent


class PlannerAgent(BaseAgent):
    """Creates article outline: sections, key points, target length."""

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
            "outline": parsed.get("outline", parsed),
            "sections": parsed.get("sections", []),
            "target_length": parsed.get("target_length", 1500),
        }
