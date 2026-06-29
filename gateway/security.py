"""Security — input validation, sanitization, API key protection."""

from __future__ import annotations

import os
import re
from typing import Any


class SecurityGuard:
    """Basic security layer for LLM inputs/outputs."""

    MAX_INPUT_LENGTH = 8000  # tokens approx
    DANGEROUS_PATTERNS = [
        r"ignore previous instructions",
        r"ignore all prior",
        r"you are now",
        r"system prompt",
        r"reveal your prompt",
    ]

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.max_input_length = config.get("max_input_length", self.MAX_INPUT_LENGTH)
        self.check_injection = config.get("check_injection", True)

    def validate_input(self, text: str) -> tuple[bool, str]:
        """Validate input text. Returns (is_safe, reason)."""
        if len(text) > self.max_input_length:
            return False, f"Input too long: {len(text)} > {self.max_input_length}"

        if self.check_injection:
            for pattern in self.DANGEROUS_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    return False, f"Potential prompt injection detected"

        return True, ""

    def sanitize_input(self, text: str) -> str:
        """Remove potentially harmful content."""
        # Remove null bytes
        text = text.replace("\x00", "")
        # Limit length
        text = text[:self.max_input_length]
        return text

    def validate_output(self, text: str) -> tuple[bool, str]:
        """Basic output validation."""
        if not text or not text.strip():
            return False, "Empty output"
        return True, ""

    @staticmethod
    def get_api_key(env_var: str) -> str | None:
        """Safely get API key from env, return None if missing."""
        key = os.environ.get(env_var)
        if not key:
            return None
        # Don't log or return full key
        return key
