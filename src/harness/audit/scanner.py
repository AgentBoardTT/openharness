"""PIIScanner — regex-based PII and secret detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ScanResult:
    """A single PII/secret finding."""

    pattern_name: str
    match: str
    start: int
    end: int


# Pre-compiled patterns for common PII and secrets
_DEFAULT_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.ASCII),
    "phone_us": re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_secret_key": re.compile(
        r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key\s*[:=]\s*[A-Za-z0-9/+=]{40}"
    ),
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "slack_token": re.compile(r"\bxox[bpras]-[A-Za-z0-9-]{10,}\b"),
    "private_key_header": re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
    "generic_api_key": re.compile(
        r"(?i)(?:api[_\-]?key|apikey|secret[_\-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?"
    ),
    "ip_address": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
}


class PIIScanner:
    """Scans text for PII and secrets using configurable regex patterns."""

    def __init__(
        self,
        *,
        custom_patterns: dict[str, str] | None = None,
        disabled_patterns: set[str] | None = None,
    ) -> None:
        self._patterns: dict[str, re.Pattern[str]] = {}
        disabled = disabled_patterns or set()

        for name, pattern in _DEFAULT_PATTERNS.items():
            if name not in disabled:
                self._patterns[name] = pattern

        if custom_patterns:
            for name, raw in custom_patterns.items():
                self._patterns[name] = re.compile(raw)

    def scan(self, text: str) -> list[ScanResult]:
        """Scan text and return all findings."""
        results: list[ScanResult] = []
        for name, pattern in self._patterns.items():
            for m in pattern.finditer(text):
                results.append(ScanResult(
                    pattern_name=name,
                    match=m.group(),
                    start=m.start(),
                    end=m.end(),
                ))
        return results

    def has_findings(self, text: str) -> bool:
        """Quick check: does the text contain any PII/secret patterns?"""
        for pattern in self._patterns.values():
            if pattern.search(text):
                return True
        return False

    def scan_dict(self, data: dict[str, Any], *, _depth: int = 0) -> list[ScanResult]:
        """Scan all string values in a dict recursively (up to 10 levels)."""
        if _depth > 10:
            return []
        results: list[ScanResult] = []
        for value in data.values():
            if isinstance(value, str):
                results.extend(self.scan(value))
            elif isinstance(value, dict):
                results.extend(self.scan_dict(value, _depth=_depth + 1))
            elif isinstance(value, (list, tuple)):
                for item in value:
                    if isinstance(item, str):
                        results.extend(self.scan(item))
                    elif isinstance(item, dict):
                        results.extend(self.scan_dict(item, _depth=_depth + 1))
        return results
