"""OutputGuard — output validation, hallucination detection, PII detection."""

from __future__ import annotations

import json
import re
from typing import Any


class OutputGuard:
    """Validates agent outputs before passing to next step."""

    # PII patterns
    PII_PATTERNS = {
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "phone_id": r"\b0[1-9][0-9]{7,11}\b",  # Indonesian phone
        "nik": r"\b[1-9][0-9]{15}\b",  # NIK 16 digits
        "credit_card": r"\b(?:\d{4}[-\s]?){3}\d{4}\b",
    }

    # Hallucination indicators — phrases that signal uncertain/made-up content
    HALLUCINATION_SIGNALS = [
        r"as of my (knowledge|training) (cutoff|date)",
        r"I don'?t have (access|real-time)",
        r"I cannot (verify|confirm|guarantee)",
        r"this (may|might|could) not be accurate",
        r"please (verify|check|confirm) this",
        r"I'?m not sure (about|if)",
    ]

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.detect_pii = config.get("detect_pii", True)
        self.detect_hallucination = config.get("detect_hallucination", True)
        self._pii_compiled = {k: re.compile(v) for k, v in self.PII_PATTERNS.items()}
        self._hall_compiled = [re.compile(p, re.IGNORECASE) for p in self.HALLUCINATION_SIGNALS]

    def validate_json(self, text: str) -> tuple[bool, dict[str, Any] | None, str]:
        """
        Try to parse text as JSON.
        Returns (success, parsed_dict_or_None, error_message).
        """
        try:
            data = json.loads(text)
            return True, data, ""
        except json.JSONDecodeError:
            # Try extracting from markdown code block
            match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
            if match:
                try:
                    data = json.loads(match.group(1).strip())
                    return True, data, ""
                except json.JSONDecodeError:
                    pass
            return False, None, "Output is not valid JSON"

    def detect_pii_in_text(self, text: str) -> list[str]:
        """
        Scan text for PII. Returns list of PII types found.
        """
        if not self.detect_pii:
            return []
        found = []
        for pii_type, pattern in self._pii_compiled.items():
            if pattern.search(text):
                found.append(pii_type)
        return found

    def check_hallucination_signals(self, text: str) -> list[str]:
        """
        Check for hallucination indicators in text.
        Returns list of matched signals.
        """
        if not self.detect_hallucination:
            return []
        found = []
        for pattern in self._hall_compiled:
            match = pattern.search(text)
            if match:
                found.append(match.group(0))
        return found

    def redact_pii_in_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact PII in a dictionary/list/string structure."""
        if not self.detect_pii:
            return data

        if isinstance(data, str):
            redacted = data
            for pii_type, pattern in self._pii_compiled.items():
                if pii_type == "email":
                    redacted = pattern.sub("[EMAIL_REDANTED]", redacted)
                elif pii_type == "phone_id":
                    redacted = pattern.sub("[PHONE_REDANTED]", redacted)
                elif pii_type == "nik":
                    redacted = pattern.sub("[NIK_REDANTED]", redacted)
                elif pii_type == "credit_card":
                    redacted = pattern.sub("[CARD_REDANTED]", redacted)
            return redacted
        elif isinstance(data, dict):
            return {k: self.redact_pii_in_dict(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self.redact_pii_in_dict(item) for item in data]
        return data

    def validate_output(self, output: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Full output validation. Returns (is_valid, list_of_warnings).
        Warnings don't block the output but are logged.
        """
        warnings = []

        if not output:
            return False, ["Empty output"]

        # Flatten to text for scanning
        full_text = json.dumps(output, ensure_ascii=False)

        # PII check
        pii_found = self.detect_pii_in_text(full_text)
        if pii_found:
            warnings.append(f"PII detected in output: {', '.join(pii_found)} (Redacting in final output)")

        # Hallucination check
        signals = self.check_hallucination_signals(full_text)
        if signals:
            warnings.append(f"Possible hallucination signals: {signals[:2]}")

        return True, warnings

