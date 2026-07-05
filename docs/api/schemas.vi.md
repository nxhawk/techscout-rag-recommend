# Schema Request & Response

Tất cả schema được định nghĩa dưới dạng Pydantic model trong `api/schemas.py`.

## Request Models

### RecommendRequest

```python
class RecommendRequest(BaseModel):
    query: str                    # Truy vấn ngôn ngữ tự nhiên
    top_k: int = 5               # Số lượng kết quả
    filters: dict | None = None  # Ghi đè filter tùy chọn
```

### CompareRequest

```python
class CompareRequest(BaseModel):
    query: str | None = None           # Truy vấn so sánh bằng ngôn ngữ tự nhiên
    product_ids: list[str] | None = None  # Hoặc ID sản phẩm cụ thể
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
    recommendations: list[dict]  # Danh sách sản phẩm đã xếp hạng
    summary: str = ""            # Tóm tắt tổng quan
```

### CompareResponse

```python
class CompareResponse(BaseModel):
    comparison_table: dict       # Bảng thông số đã đối chiếu
    analysis: dict               # Phân tích của LLM
    conclusion: str = ""         # Kết luận cuối cùng
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
