# Request & Response Schemas

All schemas are defined as Pydantic models in `api/schemas.py`.

## Request Models

### RecommendRequest

```python
class RecommendRequest(BaseModel):
    query: str                    # Natural language query
    top_k: int = 5               # Number of results
    filters: dict | None = None  # Optional filter overrides
```

### CompareRequest

```python
class CompareRequest(BaseModel):
    query: str | None = None           # NL comparison query
    product_ids: list[str] | None = None  # Or specific product IDs
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
    recommendations: list[dict]  # Ranked product list
    summary: str = ""            # Overall summary
```

### CompareResponse

```python
class CompareResponse(BaseModel):
    comparison_table: dict       # Aligned specs table
    analysis: dict               # LLM analysis
    conclusion: str = ""         # Final verdict
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
