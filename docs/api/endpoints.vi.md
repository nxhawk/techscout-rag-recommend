# API Endpoints

Base URL: `http://localhost:8000`

## Health Check

```
GET /health
```

**Response:**
```json
{"status": "ok"}
```

## Gợi ý sản phẩm

```
POST /api/recommend
```

Tìm các sản phẩm khớp với truy vấn ngôn ngữ tự nhiên của người dùng và sinh
lời giải thích bằng tiếng Việt (do LLM viết) về lý do mỗi sản phẩm phù hợp.

**Request Body:**

| Trường    | Kiểu   | Bắt buộc | Mặc định | Mô tả                    |
| --------- | ------ | -------- | ------- | ------------------------------ |
| `query`   | string | Có      | —       | Truy vấn sản phẩm bằng ngôn ngữ tự nhiên (tiếng Việt hoặc tiếng Anh). 1–2000 ký tự, chỉ toàn khoảng trắng sẽ bị từ chối |
| `top_k`   | int    | Không       | 5       | Số lượng gợi ý. Phải trong khoảng 1–10 |
| `filters` | object | Không       | null    | Dành cho tương lai — hiện tại filter được trích xuất tự động từ `query` bởi `FilterEngine`. Chỉ chấp nhận các key trong whitelist: `brand`, `category`, `price_min`, `price_max`, `min_rating`, `tags` — key khác sẽ trả về `422` |

Ngoài các kiểm tra ở tầng field, `query` còn đi qua [guardrail đầu vào](../architecture/guardrails.vi.md)
(normalize → heuristic độ dài/URL/code → denylist prompt injection) trước khi
vào bước truy xuất.

Các filter được trích xuất từ truy vấn và áp dụng **ngay tại tầng vector
store** (sản phẩm không đạt sẽ không bao giờ đến được LLM):

| Filter        | Ví dụ cụm từ                                                |
| ------------- | ----------------------------------------------------------- |
| Khoảng giá    | "dưới 15 triệu", "tầm 10 triệu", "từ 10 đến 20 triệu", "under 15 million", "from 10 to 20 million", "around 10 million" |
| Thương hiệu   | "Samsung", "iPhone" (được quy về thương hiệu chuẩn)          |
| Danh mục      | "điện thoại"/"phone" → smartphone, "laptop", "tai nghe", ... |
| Rating tối thiểu | "đánh giá tốt", "rating cao" → ≥ 4.0                     |

**Ví dụ:**

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Phone with great camera under 15 million VND", "top_k": 3}'
```

**Response:**

| Trường            | Kiểu     | Mô tả                                              |
| ----------------- | -------- | -------------------------------------------------- |
| `recommendations` | array    | Danh sách sản phẩm đã xếp hạng kèm lý do (xem bên dưới) |
| `summary`         | string   | Tóm tắt chung về các gợi ý (tiếng Việt)            |
| `warnings`        | string[] | Ghi chú tiếng Việt về những gì guardrail đã sanitize, loại bỏ hoặc thay thế (rỗng nếu không có gì xảy ra) |

```json
{
  "recommendations": [
    {
      "name": "Xiaomi 14",
      "price": 13990000,
      "reason": "Leica camera system with competitive pricing",
      "pros": ["Leica camera quality", "Great value", "90W fast charging"],
      "cons": ["HyperOS has ads"],
      "best_for": "Photography enthusiasts on a budget"
    }
  ],
  "summary": "Top picks based on camera quality within your budget",
  "warnings": []
}
```

LLM được gọi ở chế độ **JSON mode gốc** (Gemini `response_mime_type`,
OpenAI `response_format`) nên output luôn là JSON parse được, không có đoạn
văn mở đầu. Response sau đó đi qua [guardrail đầu ra](../architecture/guardrails.vi.md):
được validate theo schema Pydantic và mỗi gợi ý được **grounding** đối chiếu
với sản phẩm đã truy xuất (tên sản phẩm bị LLM "bịa" sẽ bị loại bỏ). Nếu
validate thất bại hoặc không còn gợi ý nào sau grounding, endpoint vẫn trả về
`200` với một fallback tất định dựng từ các sản phẩm xếp hạng cao nhất —
không bao giờ trả lỗi — và `warnings` giải thích chuyện gì đã xảy ra.

**Lỗi:**

| Status | Thông báo `detail` | Ý nghĩa |
| ------ | ------------------ | ------- |
| `422`  | (FastAPI validation) | Request body không hợp lệ — `query` thiếu/rỗng/quá dài, `top_k` ngoài khoảng `1..10`, hoặc `filters` có key lạ |
| `422`  | Lý do tiếng Việt cụ thể của guardrail (ví dụ *"Yêu cầu chứa nội dung nghi vấn prompt injection/jailbreak."*) | [Guardrail đầu vào](../architecture/guardrails.vi.md) từ chối truy vấn (prompt injection, độ dài/URL/code bất thường) |
| `503`  | "Hệ thống đã hết hạn mức gọi AI…" | Hết quota LLM/embedding provider (429). API fail fast — không ngủ chờ quota — và log tóm tắt 1 dòng |
| `503`  | "Hệ thống gợi ý đang gặp sự cố…" | Sự cố pipeline khác (không kết nối được vector DB, lỗi provider…). Traceback đầy đủ được log phía server |

### Cách hoạt động

Endpoint được nối với pipeline RAG đầy đủ thông qua dependency injection của
FastAPI (`api/deps.py`):

```mermaid
sequenceDiagram
    participant C as Client
    participant A as POST /api/recommend
    participant D as get_cached_recommend_pipeline()
    participant P as RecommendPipeline
    participant V as VectorStore (pgvector)
    participant L as LLM Provider

    C->>A: {query, top_k}
    A->>D: Depends()
    Note over D: Lần gọi đầu tiên khởi tạo pipeline<br/>(embedder + vector store + LLM client),<br/>sau đó được cache bằng lru_cache
    D-->>A: RecommendPipeline
    A->>P: run(query, top_k)
    P->>P: Guardrail đầu vào (normalize/heuristics/injection)<br/>block → raise InputGuardrailBlocked
    P->>P: Phân tích ý định (ngân sách, mục đích, ưu tiên)
    P->>V: Tìm kiếm vector + filter SQL:<br/>khoảng giá, thương hiệu, danh mục (top_k × 3)
    P->>P: Chấm điểm & xếp hạng, giữ lại top_k
    P->>P: Guardrail ngữ cảnh (sanitize dữ liệu sản phẩm)
    P->>L: Prompt kèm ý định + ngữ cảnh sản phẩm<br/>(JSON mode gốc)
    L-->>P: Câu trả lời JSON chuẩn (tiếng Việt)
    P->>P: Guardrail đầu ra (validate schema + grounding,<br/>fallback khi thất bại)
    P-->>A: {recommendations, summary, warnings}
    alt guardrail đầu vào chặn
        A-->>C: 422 (lý do tiếng Việt)
    else
        A-->>C: 200 RecommendResponse
    end
```

Các chi tiết triển khai quan trọng:

1. **Việc khởi tạo pipeline được cache.** `get_cached_recommend_pipeline()`
   trong `api/deps.py` chỉ khởi tạo pipeline một lần cho mỗi process (setup
   embedder, kết nối vector DB, LLM client) và tái sử dụng cho mọi request.
2. **Route được khai báo sync (`def`) có chủ đích.** Pipeline thực hiện I/O
   blocking (truy vấn Postgres, gọi HTTP tới LLM), nên FastAPI chạy nó trong
   threadpool thay vì chặn event loop.
3. **Lỗi trả về `503` và fail fast.** API path dùng `max_retries=0` khi gọi
   provider (không ngủ chờ quota) và timeout kết nối DB 5 giây, nên dependency
   hỏng sẽ trả lời trong vài giây thay vì treo. Lỗi quota (429) được log gọn
   1 dòng; lỗi bất ngờ giữ nguyên traceback đầy đủ. Chi tiết nội bộ không bao
   giờ bị lộ trong response.
4. **Output JSON chuẩn.** LLM được gọi ở JSON mode gốc, nên response luôn
   parse được thành `recommendations` + `summary` thay vì văn xuôi tự do.
5. **Ngân sách được áp ngay từ bước truy xuất.** Filter giá/thương hiệu/danh
   mục/rating trích từ truy vấn trở thành điều kiện SQL của vector search
   (ví dụ `(metadata->>'price')::numeric <= 15000000`), nên sản phẩm vượt
   ngân sách bị loại trước khi chấm điểm và đưa vào prompt.
6. **Cấu hình** lấy từ `configs/settings.yaml` (model embedding, URL vector
   DB, provider/model LLM) và API key từ biến môi trường (`.env` được nạp khi
   khởi động). Hỗ trợ nhiều key cho mỗi provider (`GEMINI_API_KEY=key_a,key_b`
   hoặc `GEMINI_API_KEY_1=...`) và tự động xoay key khi gặp lỗi rate limit.

Về các bước bên trong pipeline (phân tích ý định, truy xuất, chấm điểm, sinh
câu trả lời) xem [Luồng xử lý](../architecture/pipeline-flow.vi.md#recommend-pipeline).

**Điều kiện tiên quyết:** dữ liệu sản phẩm phải được nạp vào vector store
trước (`uv run python scripts/ingest.py`), và API key của embedding/LLM
provider phải được đặt trong `.env` — nếu không endpoint sẽ trả về `503`.

## So sánh sản phẩm

```
POST /api/compare
```

So sánh hai hoặc nhiều sản phẩm cạnh nhau.

**Request Body:**

| Trường         | Kiểu     | Bắt buộc | Mô tả                         |
| ------------- | -------- | -------- | ----------------------------------- |
| `query`       | string   | Không       | Truy vấn so sánh bằng ngôn ngữ tự nhiên. 0–2000 ký tự |
| `product_ids` | string[] | Không       | ID sản phẩm cụ thể cần so sánh, tra cứu qua bảng catalog (source of truth). Tối đa 5, mỗi ID khớp `[a-zA-Z0-9_-]{1,64}`, ID trùng lặp bị loại bỏ |

Cung cấp `query` hoặc `product_ids` — cần ít nhất một trong hai (`422` nếu
thiếu cả hai). `query` cũng đi qua cùng [guardrail đầu vào](../architecture/guardrails.vi.md)
như `/api/recommend`; chỉ dùng `product_ids` thì bỏ qua bước kiểm tra này
(không có truy vấn dạng text tự do để validate).

**Ví dụ:**

```bash
curl -X POST http://localhost:8000/api/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "Compare iPhone 15 Pro Max vs Samsung Galaxy S24 Ultra"}'
```

**Response:**

| Trường              | Kiểu     | Mô tả                                        |
| ------------------- | -------- | --------------------------------------------------- |
| `comparison_table`  | object   | Bảng thông số đã đối chiếu (output của `SpecAligner`) |
| `analysis`          | object   | Phân tích của LLM: `criteria_comparison`, `product_analysis` |
| `conclusion`        | string   | Kết luận cuối cùng (tiếng Việt)                      |
| `warnings`          | string[] | Ghi chú tiếng Việt về những gì guardrail đã sanitize, loại bỏ hoặc thay thế |

```json
{
  "comparison_table": {
    "fields": ["processor", "ram", "battery", "rear_camera"],
    "products": [...]
  },
  "analysis": {
    "criteria_comparison": [...],
    "product_analysis": [...]
  },
  "conclusion": "Summary of which product suits which use case",
  "warnings": []
}
```

Cơ chế [guardrail đầu ra](../architecture/guardrails.vi.md) tương tự
`/api/recommend`: JSON của LLM được validate theo schema và mỗi
`product_analysis[].name` được grounding đối chiếu với các sản phẩm thực sự
đang so sánh. Nếu thất bại, endpoint vẫn trả về `200` với fallback tất định
dựng từ bảng so sánh — không bao giờ trả lỗi.

**Lỗi:**

| Status | Thông báo `detail` | Ý nghĩa |
| ------ | ------------------ | ------- |
| `422`  | (FastAPI validation) | Request body không hợp lệ — thiếu cả `query` lẫn `product_ids`, `product_ids` sai định dạng/quá nhiều, hoặc `query` quá dài |
| `422`  | Lý do tiếng Việt cụ thể của guardrail | [Guardrail đầu vào](../architecture/guardrails.vi.md) từ chối `query` (prompt injection, độ dài/URL/code bất thường) |
| `422`  | "Cần ít nhất 2 sản phẩm để so sánh." | Không đủ 2 sản phẩm được xác định từ `product_ids`/`query` |
| `503`  | "Hệ thống đã hết hạn mức gọi AI…" | Hết quota LLM/embedding provider (429) |
| `503`  | "Hệ thống so sánh đang gặp sự cố…" | Sự cố pipeline khác (không kết nối được vector DB, lỗi provider…) |

**Điều kiện tiên quyết:** giống `/api/recommend` — sản phẩm phải được nạp
trước, và tra cứu `product_ids` cần bảng catalog (`product_catalog`) đã có dữ
liệu (qua API CRUD hoặc `scripts/ingest.py`).

## Tìm kiếm sản phẩm

```
POST /api/search
```

Tìm kiếm sản phẩm theo truy vấn kèm filter tùy chọn.

**Request Body:**

| Trường    | Kiểu   | Bắt buộc | Mặc định | Mô tả            |
| --------- | ------ | -------- | ------- | ---------------------- |
| `query`   | string | Có      | —       | Truy vấn tìm kiếm           |
| `filters` | object | Không       | null    | Filter metadata       |
| `limit`   | int    | Không       | 10      | Số kết quả tối đa trả về  |

**Response:**

```json
{
  "results": [
    {
      "id": "iphone-15-pro-max",
      "document": "iPhone 15 Pro Max - Apple...",
      "metadata": {"brand": "Apple", "price": 29990000},
      "score": 0.92
    }
  ],
  "total": 1
}
```

## Quản lý sản phẩm (CRUD)

Catalog là **source of truth**: các endpoint này chỉ ghi vào bảng
`product_catalog`. Debezium (CDC) bắt thay đổi từ WAL và các sync worker tự
lan truyền sang Elasticsearch + pgvector — thường trong vài giây (eventual
consistency).

### Tạo mới

```
POST /api/products            → 201
```

| Trường | Kiểu | Bắt buộc | Mô tả |
| ------ | ---- | -------- | ----- |
| `product_id` | string | Không | Tự sinh từ `name` nếu bỏ trống |
| `name` | string | Có | Tên sản phẩm |
| `brand`, `category`, `description`, `review_summary`, `currency` | string | Không | Các trường text |
| `price` | int ≥ 0 | Không | Giá (VND) |
| `specifications` | object | Không | Thông số kỹ thuật |
| `pros`, `cons`, `tags` | string[] | Không | Danh sách |
| `avg_rating` | float 0–5 | Không | Điểm đánh giá trung bình |
| `review_count` | int ≥ 0 | Không | Số lượt đánh giá |

```bash
curl -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{"product_id": "xiaomi-15", "name": "Xiaomi 15", "brand": "Xiaomi",
       "category": "smartphone", "price": 18990000,
       "description": "Snapdragon 8 Elite, camera Leica."}'
```

**Response:** `{"product_id": "xiaomi-15", "message": "Đã tạo sản phẩm. Dữ liệu tìm kiếm sẽ được đồng bộ trong giây lát."}`

`409` nếu id đã tồn tại.

### Cập nhật (partial)

```
PUT /api/products/{product_id}
```

Chỉ gửi các trường cần đổi. Thay đổi chỉ giá/rating được lan truyền bằng
update metadata rẻ (không re-embed); thay đổi text sẽ re-embed các chunk
của sản phẩm.

```bash
curl -X PUT http://localhost:8000/api/products/xiaomi-15 \
  -H "Content-Type: application/json" -d '{"price": 17490000}'
```

`404` nếu sản phẩm không tồn tại; `422` nếu body rỗng.

### Xóa

```
DELETE /api/products/{product_id}
```

Xóa sản phẩm khỏi catalog; CDC gỡ khỏi cả hai index tìm kiếm. `404` nếu
không tồn tại.

### Đọc

```
GET /api/products/{product_id}
GET /api/products?limit=50&offset=0
```

Đọc thẳng catalog (luôn nhất quán mạnh — không có độ trễ index).
