"""Sanitize retrieved product data before it is embedded into an LLM prompt.

Retrieved documents/descriptions come from crawled third-party sources and
must be treated as untrusted text: strip HTML/script, strip sentences that
look like embedded instructions ("ignore previous instructions ..." hidden
inside a product description), and truncate so a single field cannot blow
out the prompt budget.
"""

import re
from collections.abc import Sequence
from typing import Any

from src.guardrails.config import GuardrailConfig

_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_INSTRUCTION_RE = re.compile(
    r"(ignore (all |any )?(the )?previous instructions"
    r"|system prompt\s*:"
    r"|you are now (a|an) "
    r"|new instructions\s*:"
    r"|bo qua (toan bo |het )?(cac )?(huong dan|chi dan) (truoc|phia tren))",
    re.IGNORECASE,
)
_WHITESPACE_RE = re.compile(r"\s+")

#: Fields commonly holding free-form third-party text; these get sanitized
#: and length-truncated. Everything else in ``sanitize_product_fields`` is
#: passed through unchanged (numbers, ids, ratings, ...).
DEFAULT_TEXT_FIELDS: tuple[str, ...] = ("document", "description", "review_summary")


def sanitize_text_field(text: Any, *, max_len: int | None = None) -> str:
    """Strip HTML/script tags and embedded-instruction sentences, truncate."""
    if not isinstance(text, str) or not text:
        return ""
    cleaned = _SCRIPT_RE.sub("", text)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = _INSTRUCTION_RE.sub("[da loc noi dung khong hop le]", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    if max_len is not None and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "..."
    return cleaned


def sanitize_product_fields(
    product: dict[str, Any],
    fields: Sequence[str],
    *,
    text_fields: Sequence[str] = DEFAULT_TEXT_FIELDS,
    config: GuardrailConfig | None = None,
) -> dict[str, Any]:
    """Project ``product`` onto a whitelist of fields, sanitizing text ones.

    Only fields the prompt actually needs (name/brand/price/spec/rating)
    should be passed in ``fields`` - this avoids dumping an entire crawled
    document blob into the prompt.
    """
    cfg = config or GuardrailConfig()
    result: dict[str, Any] = {}
    for name in fields:
        value = product.get(name)
        if name in text_fields:
            value = sanitize_text_field(value, max_len=cfg.max_context_field_chars)
        result[name] = value
    return result
