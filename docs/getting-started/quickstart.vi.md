# Bắt đầu nhanh

## Khuyến nghị: Khởi động toàn bộ stack với Docker

Cách nhanh nhất để chạy mọi thứ là Docker Compose. Từ thư mục `docker/`:

```bash
cd docker
docker compose up --build
```

Lệnh này khởi động **toàn bộ stack**, không chỉ API:

- **app** — FastAPI server trên cổng `8000`
- **postgres** — Postgres + pgvector: bảng `product_catalog` (source of truth) cùng vector index, khởi động với `wal_level=logical` cho CDC
- **elasticsearch** — index keyword BM25 (`product_chunks`) trên cổng `9200`
- **kafka** — event stream single-node KRaft trên cổng `9092`
- **connect** — Debezium (Kafka Connect) trên cổng `8083`, bắt thay đổi của `product_catalog`
- **connect-init** — job chạy một lần: đăng ký Debezium connector một cách idempotent rồi thoát
- **indexer-worker** — CDC consumer giữ Elasticsearch luôn fresh
- **embedding-worker** — CDC consumer giữ pgvector luôn fresh
- **redis** — cache trên cổng `6379`

API có sẵn tại `http://localhost:8000`, tài liệu tương tác tại `http://localhost:8000/docs`. Xem [hướng dẫn triển khai Docker](../deployment/docker.vi.md) để biết chi tiết đầy đủ về volume và các lệnh vòng đời.

Sau khi stack đã lên, nạp dữ liệu mẫu bên trong container đang chạy:

```bash
docker compose exec app uv run python scripts/seed.py
docker compose exec app uv run python scripts/ingest.py
```

## Thiết lập thủ công / tối giản

Nếu bạn chỉ muốn phần lõi (không chạy app bằng Docker), có thể chạy các service phụ trợ và API riêng.

### 1. Khởi động Postgres (pgvector)

Tối thiểu bạn cần Postgres với pgvector. Tùy chọn thêm Elasticsearch, Kafka và Debezium Connect nếu muốn keyword search đầy đủ dựa trên CDC:

```bash
cd docker

# Chỉ phần lõi — Postgres
docker compose up -d postgres

# Hoặc toàn bộ stack phụ trợ cho keyword search qua CDC
docker compose up -d postgres elasticsearch kafka connect connect-init
```

Mặc định app kết nối tới `postgresql://postgres:postgres@localhost:5432/rag_products`. Có thể override bằng biến môi trường `DATABASE_URL` hoặc `vector_db_url` trong `configs/settings.yaml`.

!!! note "Retrieval khi không có Elasticsearch"
    Nếu bạn chạy mà không có Elasticsearch và Kafka, retrieval vẫn hoạt động: API tự động fallback sang index BM25 in-memory cho nhánh keyword của hybrid search.

### 2. Nạp dữ liệu mẫu

Có hai chế độ ingestion:

```bash
# Mặc định: ghi cả ba đích — product_catalog, pgvector, và Elasticsearch
uv run python scripts/ingest.py

# Chỉ catalog: chỉ ghi product_catalog và để các sync worker CDC
# xây cả hai index từ Debezium initial snapshot
uv run python scripts/ingest.py --catalog-only
```

Chế độ mặc định đọc sản phẩm từ `data/raw/`, chia nhỏ theo từng trường (mô tả, thông số, ưu/nhược điểm, đánh giá), sinh embedding, ghi vector vào pgvector, bulk-upsert index keyword vào Elasticsearch (bỏ qua nếu ES đang down), và ghi source of truth `product_catalog`. Chế độ `--catalog-only` chỉ ghi catalog; các sync worker đang chạy sau đó tự xây Elasticsearch và pgvector từ CDC snapshot.

### 3. Khởi động API Server

```bash
uv run uvicorn api.app:app --reload
```

Server chạy tại `http://localhost:8000`. Tài liệu tương tác có sẵn tại `http://localhost:8000/docs`.

## Thử gợi ý sản phẩm

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Phone with great camera under 15 million VND", "top_k": 3}'
```

## Thử so sánh sản phẩm

```bash
curl -X POST http://localhost:8000/api/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "Compare iPhone 15 Pro Max vs Samsung Galaxy S24 Ultra"}'
```

## Thử tìm kiếm

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "gaming laptop with RTX 4060", "top_k": 5}'
```

## Quản lý catalog (CRUD)

Bảng `product_catalog` là source of truth. Tạo một sản phẩm qua API CRUD và thay đổi sẽ tự lan truyền sang các index tìm kiếm qua CDC:

```bash
curl -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Phone 15",
    "brand": "ExampleBrand",
    "category": "phone",
    "price": 12990000,
    "description": "A mid-range phone with a great camera."
  }'
```

Chỉ trong vài giây, pipeline Debezium → Kafka → sync worker cập nhật cả Elasticsearch và pgvector, nên sản phẩm mới có thể tìm kiếm được mà không cần ingest lại thủ công.

## Chạy Tests

```bash
uv run pytest tests/
```
