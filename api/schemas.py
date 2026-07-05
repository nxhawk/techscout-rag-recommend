"""API Schemas - Request/Response models."""
from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict | None = None

class RecommendResponse(BaseModel):
    recommendations: list[dict]
    summary: str = ""

class CompareRequest(BaseModel):
    query: str | None = None
    product_ids: list[str] | None = None

class CompareResponse(BaseModel):
    comparison_table: dict
    analysis: dict
    conclusion: str = ""

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
