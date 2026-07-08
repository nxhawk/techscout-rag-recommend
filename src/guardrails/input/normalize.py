"""Normalize guardrail - strip control chars, collapse whitespace, NFC."""

import re
import unicodedata

from src.guardrails.base import BaseGuardrail
from src.guardrails.types import GuardrailResult

# C0/C1 control chars except tab/newline (kept, then collapsed by whitespace
# regex below), plus DEL.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Unicode-normalize and strip control chars / redundant whitespace."""
    text = unicodedata.normalize("NFC", text or "")
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


class NormalizeGuardrail(BaseGuardrail):
    """Always-sanitize guardrail: never blocks, only cleans the text."""

    name = "normalize"

    def check(self, text: str) -> GuardrailResult:
        cleaned = normalize_text(text)
        warnings = []
        if cleaned != (text or "").strip():
            warnings.append("Da chuan hoa ky tu dieu khien/khoang trang trong noi dung.")
        return GuardrailResult.sanitize(sanitized_text=cleaned, warnings=warnings)
