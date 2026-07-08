# Request & Response Schemas

All schemas are defined as Pydantic models in `api/schemas.py`. Field-level
constraints here are the first of several [guardrail](../architecture/guardrails.md)
layers — they reject malformed requests as a plain `422` before any pipeline
or LLM work happens; deeper rule-based checks (prompt injection, output
grounding) run inside the pipelines and are documented on the
[Guardrails](../architecture/guardrails.md) page.

## Request Models

### RecommendRequest

```python
ALLOWED_FILTER_KEYS = {"brand", "category", "price_min", "price_max", "min_rating", "tags"}

class RecommendRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)  # trimmed; blank -> 422
    top_k: int = Field(default=5, ge=1, le=10)
    filters: dict | None = None   # keys outside ALLOWED_FILTER_KEYS -> 422
```

### CompareRequest

```python
class CompareRequest(BaseModel):
    query: str | None = Field(default=None, max_length=2000)          # trimmed
    product_ids: list[str] | None = Field(default=None, max_length=5)  # each ^[a-zA-Z0-9_-]{1,64}$, deduped
    # model-level check: at least one of query / product_ids is required -> 422
```

### SearchRequest

```python
class SearchRequest(BaseModel):
    query: str                    # Search query
    filters: dict | None = None  # Metadata filters
    limit: int = 10              # Max results
```

## Response Models

### RecommendResponse

```python
class RecommendResponse(BaseModel):
    recommendations: list[dict]  # Ranked product list, grounded against retrieved products
    summary: str = ""            # Overall summary
    warnings: list[str] = []     # Vietnamese notes from any guardrail sanitize/fallback step
```

### CompareResponse

```python
class CompareResponse(BaseModel):
    comparison_table: dict       # Aligned specs table
    analysis: dict               # LLM analysis, grounded against compared products
    conclusion: str = ""         # Final verdict
    warnings: list[str] = []     # Vietnamese notes from any guardrail sanitize/fallback step
```

### SearchResponse

```python
class SearchResponse(BaseModel):
    results: list[dict]          # Search results with scores
    total: int = 0               # Total matches
```

## Product Catalog (CRUD) Models

These models back the `/api/products` CRUD endpoints, which write to the source-of-truth catalog (see the [Manage Products (CRUD)](endpoints.md#manage-products-crud) section of the Endpoints page and the [Data Flow](../architecture/data-flow.md) page).

### ProductCreateRequest

```python
class ProductCreateRequest(BaseModel):
    product_id: str | None = None       # Generated from name when omitted
    name: str                           # min_length=1
    brand: str = ""
    category: str = ""
    price: int = 0                      # ge=0
    currency: str = "VND"
    description: str = ""
    specifications: dict = {}
    pros: list[str] = []
    cons: list[str] = []
    review_summary: str = ""
    avg_rating: float = 0               # ge=0, le=5
    review_count: int = 0               # ge=0
    tags: list[str] = []
```

### ProductUpdateRequest

```python
class ProductUpdateRequest(BaseModel):
    # Same fields as ProductCreateRequest but ALL Optional (None default).
    # Partial update: only the provided fields change.
    product_id: str | None = None
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    price: int | None = None            # ge=0
    currency: str | None = None
    description: str | None = None
    specifications: dict | None = None
    pros: list[str] | None = None
    cons: list[str] | None = None
    review_summary: str | None = None
    avg_rating: float | None = None     # ge=0, le=5
    review_count: int | None = None     # ge=0
    tags: list[str] | None = None
```

### ProductMutationResponse

```python
class ProductMutationResponse(BaseModel):
    product_id: str
    message: str
```

### ProductResponse

```python
class ProductResponse(BaseModel):
    product: dict
```

### ProductListResponse

```python
class ProductListResponse(BaseModel):
    products: list[dict]
    total: int = 0
```
