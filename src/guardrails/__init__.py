"""Non-LLM guardrails for the recommend/compare pipelines.

Three stages, one contract (``GuardrailResult``: ``allow`` / ``sanitize`` /
``block``):

- ``input``   - reject/clean the raw user query before retrieval.
- ``context`` - sanitize retrieved product text before it enters the prompt.
- ``output``  - validate the LLM's JSON against a Pydantic schema, then
                ground every item against retrieved/compared products.
                On failure, ``fallback`` builds a deterministic response
                (no second LLM call) so the API always returns valid data.

Extending this package:

- New input check: subclass ``BaseGuardrail`` in ``input/``, add it to
  ``input.build_input_chain``.
- New output field/shape: update the matching model in ``output/schemas.py``
  (keep it in sync with the prompt template's JSON contract).
- New limits: add a field to ``GuardrailConfig`` instead of hardcoding a
  number in a guardrail module.
"""

from src.guardrails.base import BaseGuardrail, GuardrailChain
from src.guardrails.config import GuardrailConfig
from src.guardrails.context.sanitizer import sanitize_product_fields, sanitize_text_field
from src.guardrails.exceptions import InputGuardrailBlocked
from src.guardrails.fallback import build_compare_fallback, build_recommend_fallback
from src.guardrails.input import build_input_chain
from src.guardrails.logging_utils import log_guardrail_event
from src.guardrails.output import (
    ground_compare_analysis,
    ground_recommendations,
    validate_compare_output,
    validate_recommend_output,
)
from src.guardrails.types import GuardrailAction, GuardrailResult

__all__ = [
    "BaseGuardrail",
    "GuardrailAction",
    "GuardrailChain",
    "GuardrailConfig",
    "GuardrailResult",
    "InputGuardrailBlocked",
    "build_compare_fallback",
    "build_input_chain",
    "build_recommend_fallback",
    "ground_compare_analysis",
    "ground_recommendations",
    "log_guardrail_event",
    "sanitize_product_fields",
    "sanitize_text_field",
    "validate_compare_output",
    "validate_recommend_output",
]
