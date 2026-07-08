"""Input guardrails - rule/heuristic checks applied to raw user queries.

Order matters: normalize first (so downstream regex checks see clean text),
then reject outright malicious content (injection), then heuristic risk
scoring (length/URLs/code/repeated chars). See ``build_input_chain``.
"""

from src.guardrails.base import GuardrailChain
from src.guardrails.config import GuardrailConfig
from src.guardrails.input.heuristics import HeuristicGuardrail
from src.guardrails.input.injection import InjectionGuardrail
from src.guardrails.input.normalize import NormalizeGuardrail, normalize_text

__all__ = [
    "NormalizeGuardrail",
    "InjectionGuardrail",
    "HeuristicGuardrail",
    "normalize_text",
    "build_input_chain",
]


def build_input_chain(config: GuardrailConfig | None = None) -> GuardrailChain:
    """Build the default input-guardrail chain (used by both pipelines)."""
    cfg = config or GuardrailConfig()
    return GuardrailChain(
        [
            NormalizeGuardrail(),
            HeuristicGuardrail(cfg),
            InjectionGuardrail(),
        ]
    )
