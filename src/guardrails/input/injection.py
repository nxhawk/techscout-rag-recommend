"""Injection/jailbreak guardrail - regex denylist, case-insensitive.

Deliberately simple and dependency-free (no LLM call). Patterns cover both
English and Vietnamese phrasings of "ignore your instructions" / "reveal
your system prompt" style attacks. Extend ``DEFAULT_INJECTION_PATTERNS`` to
add new phrasings; each entry is a raw regex string.
"""

import re

from src.guardrails.base import BaseGuardrail
from src.guardrails.types import GuardrailResult

DEFAULT_INJECTION_PATTERNS: list[str] = [
    # English
    r"ignore (all |any )?(the )?previous instructions",
    r"disregard (all |any )?(the )?(previous |above )?instructions",
    r"you are now (a|an) ",
    r"new instructions\s*:",
    r"system prompt\s*:",
    r"reveal (your |the )?(system )?prompt",
    r"jailbreak",
    r"dan mode",
    # Vietnamese
    r"bo qua (toan bo |het )?(cac )?(huong dan|chi dan|yeu cau) (truoc|phia tren)",
    r"quen (het |toan bo )?(huong dan|chi dan)",
    r"tu bay gio (ban|hay) la",
    r"tiet lo (system prompt|prompt he thong|huong dan he thong)",
]


class InjectionGuardrail(BaseGuardrail):
    """Blocks queries matching known prompt-injection / jailbreak phrasing."""

    name = "injection"

    def __init__(self, patterns: list[str] | None = None):
        self._patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in (patterns or DEFAULT_INJECTION_PATTERNS)
        ]

    def check(self, text: str) -> GuardrailResult:
        for pattern in self._patterns:
            if pattern.search(text or ""):
                return GuardrailResult.block(
                    reason="Yeu cau chua noi dung nghi van prompt injection/jailbreak."
                )
        return GuardrailResult.allow(sanitized_text=text)
