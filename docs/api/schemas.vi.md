# Schema Request & Response

Tất cả schema được định nghĩa dưới dạng Pydantic model trong `api/schemas.py`.
Các ràng buộc ở tầng field tại đây là lớp [guardrail](../architecture/guardrails.vi.md)
đầu tiên trong số nhiều lớp — chúng từ chối request sai định dạng bằng một
`422` đơn giản trước khi bất kỳ pipeline hay LLM nào chạy; các kiểm tra dựa
trên rule sâu hơn (prompt injection, grounding output) chạy bên trong
pipeline và được mô tả ở trang [Guardrail](../architecture/guardrails.vi.md).

## Request Models

### RecommendRequest

```python
ALLOWED_FILTER_KEYS = {"brand", "category", "price_min", "price_max", "min_rating", "tags"}

class RecommendRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)  # đã trim; rỗng -> 422
    top_k: int = Field(default=5, ge=1, le=10)
    filters: dict | None = None   # key ngoài ALLOWED_FILTER_KEYS -> 422
```

### CompareRequest

```python
class CompareRequest(BaseModel):
    query: str | None = Field(default=None, max_length=2000)          # đã trim
    product_ids: list[str] | None = Field(default=None, max_length=5)  # mỗi ID khớp ^[a-zA-Z0-9_-]{1,64}$, loại trùng
    # kiểm tra ở tầng model: cần ít nhất một trong query / product_ids -> 422
```

### SearchRequest

```python
class SearchRequest(BaseModel):
    query: str                    # Truy vấn tìm kiếm
    filters: dict | None = None  # Filter metadata
    limit: int = 10              # Số kết quả tối đa
```

## Response Models

### RecommendResponse

```python
class RecommendResponse(BaseModel):
    recommendations: list[dict]  # Danh sách sản phẩm đã xếp hạng, grounding với sản phẩm đã truy xuất
    summary: str = ""            # Tóm tắt tổng quan
    warnings: list[str] = []     # Ghi chú tiếng Việt từ bước sanitize/fallback của guardrail (nếu có)
```

### CompareResponse

```python
class CompareResponse(BaseModel):
    comparison_table: dict       # Bảng thông số đã đối chiếu
    analysis: dict               # Phân tích của LLM, grounding với sản phẩm đang so sánh
    conclusion: str = ""         # Kết luận cuối cùng
    warnings: list[str] = []     # Ghi chú tiếng Việt từ bước sanitize/fallback của guardrail (nếu có)
```

### SearchResponse

```python
class SearchResponse(BaseModel):
    results: list[dict]          # Kết quả tìm kiếm kèm điểm số
    total: int = 0               # Tổng số kết quả khớp
```

## Product Catalog (CRUD) Models

Các model này đứng sau các endpoint CRUD `/api/products`, vốn chỉ ghi vào catalog là source of truth (xem mục [Quản lý sản phẩm (CRUD)](endpoints.vi.md#quan-ly-san-pham-crud) trên trang Endpoints và trang [Luồng dữ liệu](../architecture/data-flow.vi.md)).

### ProductCreateRequest

```python
class ProductCreateRequest(BaseModel):
    product_id: str | None = None       # Tự sinh từ name khi bỏ trống
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
    # Cùng các trường như ProductCreateRequest nhưng TẤT CẢ đều Optional (mặc định None).
    # Cập nhật partial: chỉ các trường được gửi lên mới thay đổi.
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
