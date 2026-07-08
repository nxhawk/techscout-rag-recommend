"""Output guardrails - schema validation + grounding for LLM responses."""

from src.guardrails.output.grounding import ground_compare_analysis, ground_recommendations
from src.guardrails.output.schemas import CompareLLMOutput, RecommendLLMOutput
from src.guardrails.output.validator import validate_compare_output, validate_recommend_output

__all__ = [
    "RecommendLLMOutput",
    "CompareLLMOutput",
    "validate_recommend_output",
    "validate_compare_output",
    "ground_recommendations",
    "ground_compare_analysis",
]
