"""API Schemas - Request/Response models.

Field-level constraints here are the first guardrail layer (fast, free,
handled by FastAPI/Pydantic as 422 before any pipeline/LLM work). Deeper
rule-based checks (injection, heuristics) live in ``src/guardrails/`` and
run inside the pipelines - see CLAUDE.md / GUARDRAIL_PLAN.md.
"""

import re

from pydantic import BaseModel, Field, field_validator, model_validator

_MAX_QUERY_LENGTH = 2000
_MAX_PRODUCT_IDS = 5
_PRODUCT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# Whitelisted filter keys accepted by the recommend pipeline's filter engine.
ALLOWED_FILTER_KEYS = frozenset(
    {"brand", "category", "price_min", "price_max", "min_rating", "tags"}
)


class RecommendRequest(BaseModel):
    query: str = Field(min_length=1, max_length=_MAX_QUERY_LENGTH)
    top_k: int = Field(default=5, ge=1, le=10)
    filters: dict | None = None

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query khong duoc de trong.")
        return v

    @field_validator("filters")
    @classmethod
    def _filters_whitelist(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        invalid = sorted(set(v) - ALLOWED_FILTER_KEYS)
        if invalid:
            raise ValueError(f"filters chua key khong hop le: {invalid}")
        return v


class RecommendResponse(BaseModel):
    recommendations: list[dict]
    summary: str = ""
    warnings: list[str] = Field(default_factory=list)


class CompareRequest(BaseModel):
    query: str | None = Field(default=None, max_length=_MAX_QUERY_LENGTH)
    product_ids: list[str] | None = Field(default=None, max_length=_MAX_PRODUCT_IDS)

    @field_validator("query")
    @classmethod
    def _strip_query(cls, v: str | None) -> str | None:
        return v.strip() if v else v

    @field_validator("product_ids")
    @classmethod
    def _normalize_product_ids(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_id in v:
            pid = (raw_id or "").strip()
            if not pid:
                continue
            if not _PRODUCT_ID_RE.match(pid):
                raise ValueError(f"product_id khong hop le: {pid!r}")
            if pid not in seen:
                seen.add(pid)
                cleaned.append(pid)
        return cleaned

    @model_validator(mode="after")
    def _require_query_or_ids(self) -> "CompareRequest":
        if not self.query and not self.product_ids:
            raise ValueError("Can cung cap 'query' hoac 'product_ids'.")
        return self


class CompareResponse(BaseModel):
    comparison_table: dict
    analysis: dict
    conclusion: str = ""
    warnings: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str
    filters: dict | None = None
    limit: int = 10


class SearchResponse(BaseModel):
    results: list[dict]
    total: int = 0


class ProductCreateRequest(BaseModel):
    """Payload for creating a product (source-of-truth catalog)."""

    product_id: str | None = None  # generated from name when omitted
    name: str = Field(min_length=1)
    brand: str = ""
    category: str = ""
    price: int = Field(default=0, ge=0)
    currency: str = "VND"
    description: str = ""
    specifications: dict = Field(default_factory=dict)
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    review_summary: str = ""
    avg_rating: float = Field(default=0, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)


class ProductUpdateRequest(BaseModel):
    """Partial update - only provided fields are changed."""

    name: str | None = None
    brand: str | None = None
    category: str | None = None
    price: int | None = Field(default=None, ge=0)
    currency: str | None = None
    description: str | None = None
    specifications: dict | None = None
    pros: list[str] | None = None
    cons: list[str] | None = None
    review_summary: str | None = None
    avg_rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None


class ProductMutationResponse(BaseModel):
    """Result of a create/update/delete on the catalog."""

    product_id: str
    message: str


class ProductResponse(BaseModel):
    product: dict


class ProductListResponse(BaseModel):
    products: list[dict]
    total: int = 0
