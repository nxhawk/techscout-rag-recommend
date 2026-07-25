"""Guardrail thresholds - single place to tune limits used across checks.

Mirrors the style of ``src.pipeline.config.PipelineConfig``: a plain
dataclass with sane defaults that callers can override (e.g. from
``configs/settings.yaml`` in the future, or per-pipeline for tests).
"""

from dataclasses import dataclass

from src.constants import (
    MAX_COMPARE_ITEMS,
    MAX_COMPARE_PRODUCTS,
    MAX_QUERY_LENGTH,
    MAX_RECOMMENDATION_ITEMS,
)


@dataclass
class GuardrailConfig:
    """Tunable limits for input/context/output guardrails."""

    # Input (query) limits
    min_query_length: int = 1
    max_query_length: int = MAX_QUERY_LENGTH
    max_url_count: int = 3
    max_code_block_markers: int = 2  # 2 markers = 1 fenced ``` block
    repeated_char_threshold: int = 8  # e.g. "aaaaaaaa..." (8+ repeats)
    repeated_char_collapse_to: int = 3

    # Context (retrieved product text fed into the LLM prompt)
    max_context_field_chars: int = 300
    max_context_products: int = 10

    # Output (LLM response) limits
    max_recommendation_items: int = MAX_RECOMMENDATION_ITEMS
    max_compare_items: int = MAX_COMPARE_ITEMS
    max_text_field_chars: int = 2000

    # Compare-specific
    max_compare_products: int = MAX_COMPARE_PRODUCTS

    # Grounding (output/grounding.py): the prompt asks the LLM to copy a
    # product's `name` verbatim, but models still occasionally drop a
    # prefix/suffix or tweak punctuation. An exact-match-only comparison
    # made every recommendation get dropped as "ungrounded" in practice, so
    # a bounded fuzzy match is allowed before falling back to a deterministic
    # response. Still rejects genuinely different (hallucinated) names.
    grounding_min_containment_chars: int = 8  # min length for substring containment
    grounding_fuzzy_ratio: float = 0.82  # difflib.SequenceMatcher ratio cutoff
