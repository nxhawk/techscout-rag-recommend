"""Guardrail thresholds - single place to tune limits used across checks.

Mirrors the style of ``src.pipeline.config.PipelineConfig``: a plain
dataclass with sane defaults that callers can override (e.g. from
``configs/settings.yaml`` in the future, or per-pipeline for tests).
"""

from dataclasses import dataclass


@dataclass
class GuardrailConfig:
    """Tunable limits for input/context/output guardrails."""

    # Input (query) limits
    min_query_length: int = 1
    max_query_length: int = 2000
    max_url_count: int = 3
    max_code_block_markers: int = 2  # 2 markers = 1 fenced ``` block
    repeated_char_threshold: int = 8  # e.g. "aaaaaaaa..." (8+ repeats)
    repeated_char_collapse_to: int = 3

    # Context (retrieved product text fed into the LLM prompt)
    max_context_field_chars: int = 300
    max_context_products: int = 10

    # Output (LLM response) limits
    max_recommendation_items: int = 10
    max_compare_items: int = 10
    max_text_field_chars: int = 2000

    # Compare-specific
    max_compare_products: int = 5
