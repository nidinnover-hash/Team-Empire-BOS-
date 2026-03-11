"""AI data minimization — strip PII before sending to AI providers.

Replaces emails, phone numbers, SSNs, and credit card numbers with indexed
placeholders. The mapping is kept in memory so responses can be unmasked.
"""
from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}\b")
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\-\s().]{7,}\d)(?!\d)")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b")

_CATEGORY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ssn", _SSN_RE),
    ("credit_card", _CC_RE),
    ("email", _EMAIL_RE),
    ("phone", _PHONE_RE),
]


class PIIMasker:
    """Stateful PII masker with indexed placeholders and reverse mapping."""

    def __init__(self, *, allowed_categories: set[str] | None = None) -> None:
        self._allowed = allowed_categories or set()
        self._maps: dict[str, dict[str, str]] = {}  # category -> {original: placeholder}
        self._reverse: dict[str, str] = {}  # placeholder -> original
        self._counters: dict[str, int] = {}

    def _next_placeholder(self, category: str, original: str) -> str:
        # Reuse placeholder if same value already seen
        cat_map = self._maps.setdefault(category, {})
        if original in cat_map:
            return cat_map[original]

        count = self._counters.get(category, 0) + 1
        self._counters[category] = count
        placeholder = f"[{category.upper()}_{count}]"
        cat_map[original] = placeholder
        self._reverse[placeholder] = original
        return placeholder

    def mask(self, text: str) -> str:
        """Replace PII with indexed placeholders."""
        if not text:
            return text

        result = text
        for category, pattern in _CATEGORY_PATTERNS:
            if category in self._allowed:
                continue
            result = pattern.sub(
                lambda m, cat=category: self._next_placeholder(cat, m.group(0)),  # type: ignore[misc]
                result,
            )
        return result

    def unmask(self, text: str) -> str:
        """Restore placeholders back to original values."""
        if not text or not self._reverse:
            return text

        result = text
        for placeholder, original in self._reverse.items():
            result = result.replace(placeholder, original)
        return result

    def pii_categories_found(self) -> list[str]:
        """Return list of PII categories that were actually masked."""
        return [cat for cat, mapping in self._maps.items() if mapping]

    @property
    def total_masked(self) -> int:
        return sum(len(m) for m in self._maps.values())

    def summary(self) -> dict[str, Any]:
        """Return a summary suitable for audit logging."""
        return {
            "categories": self.pii_categories_found(),
            "total_masked": self.total_masked,
            "counts": {cat: len(m) for cat, m in self._maps.items() if m},
        }


def create_masker() -> PIIMasker:
    """Create a PIIMasker configured from settings."""
    from app.core.config import settings

    allowed: set[str] = set()
    raw = settings.AI_ALLOWED_PII_CATEGORIES.strip()
    if raw:
        allowed = {c.strip().lower() for c in raw.split(",") if c.strip()}
    return PIIMasker(allowed_categories=allowed)
