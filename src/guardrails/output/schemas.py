"""Pydantic models for the exact JSON contract each prompt asks the LLM for.

These mirror the ``Trả về JSON format`` block in
``src/generation/prompt_templates/recommend_prompt.py`` and
``compare_prompt.py``. Keep the two in sync: if a prompt template's JSON
contract changes, update the matching model here.
"""

from pydantic import BaseModel, Field, field_validator

_MAX_ITEMS = 20  # hard ceiling; business-logic trimming (top_k etc.) happens
# in the pipeline/grounding layer, not here.
_MAX_LIST_STR_ITEMS = 15


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _strip_list(values: object) -> object:
    if isinstance(values, list):
        return [v.strip() if isinstance(v, str) else v for v in values][:_MAX_LIST_STR_ITEMS]
    return values


class RecommendationItem(BaseModel):
    """One item of ``recommendations`` in the recommend LLM output."""

    name: str = Field(min_length=1, max_length=200)
    price: int | float | str | None = None
    reason: str = Field(default="", max_length=1000)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    best_for: str = Field(default="", max_length=300)

    @field_validator("name", "reason", "best_for", mode="before")
    @classmethod
    def _strip_str(cls, v: object) -> object:
        return _strip(v)

    @field_validator("pros", "cons", mode="before")
    @classmethod
    def _strip_lists(cls, v: object) -> object:
        return _strip_list(v)


class RecommendLLMOutput(BaseModel):
    """Full JSON contract expected from the recommend prompt."""

    recommendations: list[RecommendationItem] = Field(default_factory=list, max_length=_MAX_ITEMS)
    summary: str = Field(default="", max_length=2000)

    @field_validator("summary", mode="before")
    @classmethod
    def _strip_summary(cls, v: object) -> object:
        return _strip(v)


class CriterionComparison(BaseModel):
    """One item of ``criteria_comparison`` in the compare LLM output."""

    criterion: str = Field(min_length=1, max_length=200)
    winner: str = Field(default="", max_length=200)
    details: str = Field(default="", max_length=1000)

    @field_validator("criterion", "winner", "details", mode="before")
    @classmethod
    def _strip_str(cls, v: object) -> object:
        return _strip(v)


class ProductAnalysis(BaseModel):
    """One item of ``product_analysis`` in the compare LLM output."""

    name: str = Field(min_length=1, max_length=200)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    best_for: str = Field(default="", max_length=300)

    @field_validator("name", "best_for", mode="before")
    @classmethod
    def _strip_str(cls, v: object) -> object:
        return _strip(v)

    @field_validator("pros", "cons", mode="before")
    @classmethod
    def _strip_lists(cls, v: object) -> object:
        return _strip_list(v)


class CompareLLMOutput(BaseModel):
    """Full JSON contract expected from the compare prompt."""

    criteria_comparison: list[CriterionComparison] = Field(
        default_factory=list, max_length=_MAX_ITEMS
    )
    product_analysis: list[ProductAnalysis] = Field(default_factory=list, max_length=_MAX_ITEMS)
    conclusion: str = Field(default="", max_length=2000)

    @field_validator("conclusion", mode="before")
    @classmethod
    def _strip_conclusion(cls, v: object) -> object:
        return _strip(v)
