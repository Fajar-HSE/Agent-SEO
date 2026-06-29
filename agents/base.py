"""Base agent — all agents inherit from this."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentConfig(BaseModel):
    name: str
    provider: str = "huggingface"
    model: str = ""
    prompt_file: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    output_format: str = "json"
    confidence_threshold: float = 0.6


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.prompt_template = self._load_prompt()

    def _load_config(self, config_path: str | None) -> AgentConfig:
        """Load agent config from YAML."""
        if config_path:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return AgentConfig(**data)
        return AgentConfig(name=self.__class__.__name__)

    def _load_prompt(self) -> str:
        """Load prompt template from file."""
        if self.config.prompt_file:
            try:
                with open(self.config.prompt_file, "r", encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                logger.warning(f"Prompt file not found: {self.config.prompt_file}")
        return ""

    def _build_messages(self, input_data: dict[str, Any]) -> list[dict[str, str]]:
        """Build LLM messages from input data + prompt template."""
        system_msg = self.prompt_template or f"You are {self.config.name}."
        user_content = json.dumps(input_data, ensure_ascii=False, indent=2)
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ]

    def _parse_output(self, raw: str) -> dict[str, Any]:
        """Parse LLM output — try JSON first, fallback to raw text."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code block
            if "```json" in raw:
                start = raw.index("```json") + 7
                end = raw.index("```", start)
                return json.loads(raw[start:end])
            return {"raw_text": raw, "confidence": 0.3}

    def _calculate_confidence(self, output: dict[str, Any]) -> float:
        """Extract or calculate confidence score."""
        if "confidence" in output:
            return float(output["confidence"])
        # Heuristic: more structured output = higher confidence
        if output.get("title") and output.get("content"):
            return 0.8
        if output.get("outline") or output.get("keywords"):
            return 0.7
        return 0.5

    @abstractmethod
    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        """Execute agent logic. llm_func is the gateway completion function."""
        ...

    async def execute(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        """Public execution method with logging."""
        logger.info(f"[{self.config.name}] Starting with keys: {list(input_data.keys())}")
        try:
            result = await self.run(input_data, llm_func)
            confidence = self._calculate_confidence(result)
            result["confidence"] = confidence
            logger.info(f"[{self.config.name}] Completed — confidence: {confidence:.2f}")
            return result
        except Exception as e:
            logger.error(f"[{self.config.name}] Failed: {e}")
            raise
