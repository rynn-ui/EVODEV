"""Secret and credential redaction engine using deterministic regex and Shannon entropy."""

import math
import re
from typing import Any, Dict, List, Pattern, Tuple, Union


class SecretRedactor:
    """Detects and redacts credentials, API keys, private certificates, and secrets."""

    PATTERNS: List[Tuple[str, Pattern]] = [
        # Anthropic (test before OpenAI sk- prefix)
        ("ANTHROPIC_KEY", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
        # OpenAI
        ("OPENAI_KEY", re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
        # GitHub Tokens
        ("GITHUB_TOKEN", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b")),
        ("GITHUB_PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
        # Google API / Gemini Keys
        ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_-]{30,40}\b")),
        # AWS Access Key ID
        ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
        # Slack Webhook / Bot Token
        ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b")),
        # Generic Bearer Tokens
        ("BEARER_AUTH", re.compile(r"(?i)\bbearer\s+([a-zA-Z0-9_\-\.]{24,})\b")),
        # Private Keys (RSA, EC, PGP, etc.)
        ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----")),
        # JWT Tokens
        ("JWT_TOKEN", re.compile(r"\beyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b")),
        # Basic Auth in URLs
        ("URL_AUTH", re.compile(r"(https?://)([^:\s/]+):([^@\s/]+)@")),
        # Generic Assignment Secrets (password="...", api_key="...")
        (
            "ASSIGNMENT_SECRET",
            re.compile(
                r"(?i)(password|secret|api_?key|auth_?token|access_?token)\s*[:=]\s*['\"]([^'\"]{8,})['\"]"
            ),
        ),
    ]

    def __init__(self, entropy_threshold: float = 4.5, min_entropy_length: int = 24):
        self.entropy_threshold = entropy_threshold
        self.min_entropy_length = min_entropy_length

    def redact_text(self, text: str) -> str:
        """Scan text and replace all detected secrets with redaction labels."""
        if not text:
            return ""

        redacted = text

        # 1. Regex-based pattern matching
        for label, pattern in self.PATTERNS:
            if label == "BEARER_AUTH":
                redacted = pattern.sub(r"Bearer [REDACTED_BEARER_TOKEN]", redacted)
            elif label == "URL_AUTH":
                redacted = pattern.sub(r"\1[REDACTED_USER]:[REDACTED_PASS]@", redacted)
            elif label == "ASSIGNMENT_SECRET":
                redacted = pattern.sub(r"\1=[REDACTED_\1_SECRET]", redacted)
            else:
                redacted = pattern.sub(f"[REDACTED_{label}]", redacted)

        # 2. Entropy-based scanning for isolated candidate tokens
        redacted = self._redact_high_entropy_words(redacted)

        return redacted

    def _redact_high_entropy_words(self, text: str) -> str:
        """Find isolated alphanumeric tokens with abnormally high Shannon entropy."""
        words = re.findall(r"\b[A-Za-z0-9+/=_-]{24,}\b", text)
        for word in set(words):
            if word.startswith("[REDACTED_"):
                continue
            entropy = self.calculate_entropy(word)
            if entropy >= self.entropy_threshold:
                text = text.replace(word, "[REDACTED_HIGH_ENTROPY]")
        return text

    @staticmethod
    def calculate_entropy(s: str) -> float:
        """Calculate Shannon entropy for a string."""
        if not s:
            return 0.0
        prob = [float(s.count(c)) / len(s) for c in set(s)]
        return -sum(p * math.log2(p) for p in prob)

    def redact_data(self, data: Any) -> Any:
        """Recursively redact dictionary, list, or primitive structures."""
        if isinstance(data, str):
            return self.redact_text(data)
        elif isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                # If key itself denotes a secret, redact value directly
                if any(sec in k.lower() for sec in ["secret", "password", "token", "api_key", "auth_key"]):
                    new_dict[k] = "[REDACTED_SENSITIVE_KEY]"
                else:
                    new_dict[k] = self.redact_data(v)
            return new_dict
        elif isinstance(data, list):
            return [self.redact_data(item) for item in data]
        elif isinstance(data, tuple):
            return tuple(self.redact_data(item) for item in data)
        return data


_GLOBAL_REDACTOR = SecretRedactor()


def redact_text(text: str) -> str:
    """Convenience function to redact a string with default redactor."""
    return _GLOBAL_REDACTOR.redact_text(text)


def redact_data(data: Any) -> Any:
    """Convenience function to recursively redact data structures."""
    return _GLOBAL_REDACTOR.redact_data(data)
