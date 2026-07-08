"""Grounding guardrail - never let the LLM invent a product.

Every ``recommendations[].name`` (recommend) or ``product_analysis[].name``
(compare) must match a product that was actually retrieved/compared.
Ungrounded items are dropped and counted in a warning rather than silently
kept, so hallucinated products never reach the user.
"""

import re
from typing import Any

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_name(name: str | None) -> str:
    return _WHITESPACE_RE.sub(" ", (name or "").strip()).lower()


def _known_names(products: list[dict[str, Any]]) -> set[str]:
    names = set()
    for product in products:
        metadata = product.get("metadata")
        name = metadata.get("name") if isinstance(metadata, dict) else product.get("name")
        normalized = _normalize_name(name)
        if normalized:
            names.add(normalized)
    return names


def _ground_items(
    items: list[dict[str, Any]],
    known_names: set[str],
    *,
    dropped_message: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    grounded = []
    dropped = 0
    for item in items:
        if _normalize_name(item.get("name")) in known_names:
            grounded.append(item)
        else:
            dropped += 1
    warnings = [dropped_message.format(count=dropped)] if dropped else []
    return grounded, warnings


def ground_recommendations(
    items: list[dict[str, Any]], retrieved_products: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop recommendation items whose name doesn't match a retrieved product."""
    return _ground_items(
        items,
        _known_names(retrieved_products),
        dropped_message="Da loai {count} muc goi y khong khop voi san pham da truy xuat.",
    )


def ground_compare_analysis(
    items: list[dict[str, Any]], products: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop analysis items whose name doesn't match a product being compared."""
    return _ground_items(
        items,
        _known_names(products),
        dropped_message="Da loai {count} muc phan tich khong khop voi san pham dang so sanh.",
    )
