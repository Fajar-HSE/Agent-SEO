"""Base agent — all agents inherit from this."""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Root directory for resolving prompt paths
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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

    # Subclasses can set this to auto-load the matching prompt file.
    # e.g.  prompt_name = "keyword"  → loads prompts/keyword.txt
    prompt_name: str = ""

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)
        self.prompt_template = self._load_prompt()
        # Lazy-import security guards to avoid circular deps
        self._input_guard = None
        self._output_guard = None

    # ------------------------------------------------------------------
    # Config & prompt loading
    # ------------------------------------------------------------------

    def _load_config(self, config_path: str | None) -> AgentConfig:
        """Load agent config from YAML, or use sensible defaults."""
        if config_path and os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return AgentConfig(**data)
        return AgentConfig(name=self.prompt_name or self.__class__.__name__)

    def _load_prompt(self) -> str:
        """
        Load prompt template.
        Priority:
        1. config.prompt_file (explicit path)
        2. prompts/<prompt_name>.txt (convention-based, using class prompt_name)
        3. Empty string (fall back to generic system message)
        """
        # 1. Explicit path from config
        if self.config.prompt_file:
            path = self.config.prompt_file
            if not os.path.isabs(path):
                path = os.path.abspath(os.path.join(_ROOT, path))
            else:
                path = os.path.abspath(path)
            
            # Prevent Path Traversal
            project_root = os.path.abspath(_ROOT)
            if not path.startswith(project_root):
                logger.warning(f"Blocked path traversal attempt: {path}")
                return ""
                
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                logger.warning(f"Prompt file not found: {path}")

        # 2. Convention-based: prompts/<name>.txt
        name = self.prompt_name or (self.config.name.lower())
        convention_path = os.path.abspath(os.path.join(_ROOT, "prompts", f"{name}.txt"))
        project_root = os.path.abspath(_ROOT)
        if convention_path.startswith(project_root) and os.path.exists(convention_path):
            with open(convention_path, "r", encoding="utf-8") as f:
                return f.read()

        return ""


    # ------------------------------------------------------------------
    # Input / output helpers
    # ------------------------------------------------------------------

    def _build_messages(self, input_data: dict[str, Any]) -> list[dict[str, str]]:
        """Build LLM messages from input data + prompt template."""
        system_msg = self.prompt_template or (
            f"Kamu adalah {self.config.name}. "
            "Selalu balas dalam Bahasa Indonesia. "
            "Selalu balas dengan JSON yang valid."
        )
        # Always remind model to use Indonesian if not already in prompt
        if "BAHASA OUTPUT" not in system_msg and "Bahasa Indonesia" not in system_msg:
            system_msg = (
                "PENTING: Seluruh output WAJIB dalam Bahasa Indonesia.\n\n"
                + system_msg
            )

        # Inject language hint into input data
        enriched = dict(input_data)
        if "language" not in enriched:
            enriched["language"] = "id"

        user_content = json.dumps(enriched, ensure_ascii=False, indent=2)
        return [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
        ]

    def _parse_output(self, raw: str) -> dict[str, Any]:
        """Parse LLM output — try JSON first, fallback to raw text."""
        raw = raw.strip() if raw else ""
        
        # Direct JSON parse
        try:
            result = json.loads(raw)
            # If a string value itself contains JSON (nested), parse it too
            if isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, str) and v.strip().startswith("{"):
                        try:
                            result[k] = json.loads(v)
                        except Exception:
                            pass
            return result
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block ```json ... ```
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block in text
        match = re.search(r"\{[\s\S]+\}", raw)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # Last resort: return raw text with low confidence
        return {"raw_text": raw, "confidence": 0.3}

    def _calculate_confidence(self, output: dict[str, Any]) -> float:
        """Extract or calculate confidence score."""
        if "confidence" in output:
            return max(0.0, min(1.0, float(output["confidence"])))
        # Heuristic: more structured output = higher confidence
        if output.get("title") and output.get("content"):
            return 0.8
        if output.get("outline") or output.get("keywords"):
            return 0.7
        if "raw_text" in output:
            return 0.3
        return 0.5

    # ------------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------------

    def _get_input_guard(self):
        if self._input_guard is None:
            try:
                from security.input_guard import InputGuard
                self._input_guard = InputGuard()
            except ImportError:
                self._input_guard = False  # Security module not available
        return self._input_guard if self._input_guard is not False else None

    def _get_output_guard(self):
        if self._output_guard is None:
            try:
                from security.output_guard import OutputGuard
                self._output_guard = OutputGuard()
            except ImportError:
                self._output_guard = False
        return self._output_guard if self._output_guard is not False else None

    def _check_input(self, input_data: dict[str, Any]):
        """Run input security checks. Raises ValueError if input is unsafe."""
        guard = self._get_input_guard()
        if guard is None:
            return
        ok, reason = guard.validate_dict(input_data)
        if not ok:
            raise ValueError(f"[Security] Input rejected: {reason}")

    def _check_output(self, output: dict[str, Any]) -> list[str]:
        """Run output security checks. Returns warnings (non-blocking)."""
        guard = self._get_output_guard()
        if guard is None:
            return []
        _, warnings = guard.validate_output(output)
        for w in warnings:
            logger.warning(f"[Security] {w}")
        return warnings

    # ------------------------------------------------------------------
    # Abstract / public interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def run(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        """Execute agent logic. llm_func is the gateway completion function."""
        ...

    async def execute(self, input_data: dict[str, Any], llm_func) -> dict[str, Any]:
        """Public execution method with security checks and logging."""
        logger.info(f"[{self.config.name}] Starting with keys: {list(input_data.keys())}")

        # Security: validate input
        self._check_input(input_data)

        try:
            result = await self.run(input_data, llm_func)
            confidence = self._calculate_confidence(result)
            result["confidence"] = confidence

            # Security: check output
            warnings = self._check_output(result)
            if warnings:
                result["_warnings"] = warnings
                # Redact PII in final result if output guard is active
                guard = self._get_output_guard()
                if guard:
                    result = guard.redact_pii_in_dict(result)

            logger.info(f"[{self.config.name}] Completed — confidence: {confidence:.2f}")
            return result
        except Exception as e:
            logger.error(f"[{self.config.name}] Failed: {e}")
            raise
