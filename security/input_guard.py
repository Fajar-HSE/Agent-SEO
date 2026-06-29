"""InputGuard — prompt injection detection, input validation and sanitization."""

from __future__ import annotations

import re
from typing import Any


class InputGuard:
    """Validates and sanitizes agent inputs before sending to LLM."""

    MAX_INPUT_LENGTH = 32000  # cukup untuk artikel panjang (~8000 tokens)

    # Prompt injection patterns
    INJECTION_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"ignore\s+all\s+prior",
        r"you\s+are\s+now\s+a",
        r"forget\s+everything",
        r"disregard\s+your\s+instructions",
        r"new\s+instructions?:",
        r"system\s*prompt",
        r"reveal\s+your\s+(prompt|instructions)",
        r"act\s+as\s+if\s+you",
        r"pretend\s+(you\s+are|to\s+be)",
        r"jailbreak",
        r"DAN\s*mode",
    ]

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.max_input_length = config.get("max_input_length", self.MAX_INPUT_LENGTH)
        self.check_injection = config.get("check_injection", True)
        self._compiled = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    def validate(self, text: str) -> tuple[bool, str]:
        """
        Validate input text.
        Returns (is_safe, reason). is_safe=True means input is acceptable.
        """
        # Allow empty/None values — agents may receive empty fields
        if not text or not text.strip():
            return True, ""

        if len(text) > self.max_input_length:
            return False, f"Input too long: {len(text)} chars > {self.max_input_length} limit"

        if self.check_injection:
            for pattern in self._compiled:
                if pattern.search(text):
                    return False, "Potential prompt injection detected"

        return True, ""

    def sanitize(self, text: str) -> str:
        """Remove dangerous characters and truncate if needed."""
        # Remove null bytes and control characters (except newlines/tabs)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Truncate to limit
        text = text[: self.max_input_length]
        return text.strip()

    def validate_dict(self, data: dict[str, Any]) -> tuple[bool, str]:
        """Validate all string values in a dict."""
        for key, value in data.items():
            if isinstance(value, str):
                ok, reason = self.validate(value)
                if not ok:
                    return False, f"Field '{key}': {reason}"
        return True, ""
