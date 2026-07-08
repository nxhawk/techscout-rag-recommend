"""Output schema guardrail: parse LLM text -> validate against Pydantic model.

Flow: parse JSON (reusing ``ResponseParser``'s direct + markdown-fence
extraction) -> validate with the matching ``*LLMOutput`` model -> on any
failure return ``BLOCK`` so the caller falls back to a deterministic
response instead of surfacing malformed/partial data.
"""

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from src.generation.response_parser import ResponseParser
from src.guardrails.output.schemas import CompareLLMOutput, RecommendLLMOutput
from src.guardrails.types import GuardrailResult

_parser = ResponseParser()

_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _validate_json_output(raw_response: str, model: type[_ModelT]) -> GuardrailResult:
    data = _parser.parse_json(raw_response)
    if data is None:
        return GuardrailResult.block(reason="LLM tra ve noi dung khong phai JSON hop le.")
    if not isinstance(data, dict):
        return GuardrailResult.block(reason="LLM tra ve JSON khong dung cau truc mong doi.")
    try:
        parsed = model.model_validate(data)
    except ValidationError as exc:
        return GuardrailResult.block(
            reason=f"Output LLM khong dung schema ({exc.error_count()} loi validation)."
        )
    return GuardrailResult.allow(sanitized_payload=parsed.model_dump())


def validate_recommend_output(raw_response: str) -> GuardrailResult:
    """Validate a recommend LLM response against ``RecommendLLMOutput``."""
    return _validate_json_output(raw_response, RecommendLLMOutput)


def validate_compare_output(raw_response: str) -> GuardrailResult:
    """Validate a compare LLM response against ``CompareLLMOutput``."""
    return _validate_json_output(raw_response, CompareLLMOutput)
