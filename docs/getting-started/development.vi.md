# Hướng dẫn phát triển

Hướng dẫn này giúp bạn thiết lập dự án để phát triển cục bộ, chạy server, thực thi test, và làm việc với Docker.

## Yêu cầu

- **Python 3.11+** — bắt buộc cho dự án
- **[uv](https://docs.astral.sh/uv/)** — trình quản lý gói Python nhanh (thay thế pip)
- **Git**
- **Docker + Docker Compose** (tùy chọn, cho thiết lập containerized)

### Cài đặt uv

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

## Clone & Cài đặt

```bash
git clone https://github.com/nxhawk/rag-product-recommend.git
cd rag-product-recommend

# Cài đặt toàn bộ dependencies (bao gồm nhóm dev + docs)
uv sync --group dev --group docs
```

`uv sync` đọc `pyproject.toml`, resolve version từ `uv.lock`, và tự động tạo virtual environment. Không cần tạo venv thủ công.

## Biến môi trường

Tạo một file `.env` ở thư mục gốc của dự án và thêm (các) API key của bạn. Repo không đi kèm `.env.example`:

```dotenv
# Provider mặc định là Gemini (LLM + embedding) — đây là key duy nhất bạn cần
GEMINI_API_KEY=AIza...

# Tùy chọn — chỉ khi bạn đổi provider trong configs/settings.yaml
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Các biến override hạ tầng (đều có giá trị mặc định hợp lý)
ELASTICSEARCH_URL=http://localhost:9200
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KEYWORD_BACKEND=elasticsearch

# Môi trường
ENVIRONMENT=development
LOG_LEVEL=INFO
```

!!! tip "Tôi cần key nào?"
    Bạn chỉ cần key cho provider được cấu hình trong `configs/settings.yaml`. Mặc định dự án dùng **Gemini** cho cả LLM và embedding, nên tối thiểu bạn cần `GEMINI_API_KEY`. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` chỉ cần khi bạn đổi provider. `ELASTICSEARCH_URL`, `KAFKA_BOOTSTRAP_SERVERS`, và `KEYWORD_BACKEND` là các biến override tùy chọn cho stack CDC/keyword.

## Cấu hình

Toàn bộ cài đặt pipeline nằm trong `configs/settings.yaml`:

```yaml
# LLM provider: "gemini" | "anthropic" | "openai"
llm_provider: "gemini"
llm_model: "gemini-2.5-flash"

# Embedding provider: "gemini" | "openai"
embedding_provider: "gemini"
embedding_model: "gemini-embedding-001"

# Vector DB (Postgres + pgvector)
vector_db: "pgvector"
vector_db_url: "postgresql://postgres:postgres@localhost:5432/rag_products"  # override bằng DATABASE_URL
embedding_dim: 768

# Retrieval
top_k_retrieve: 20
top_k_recommend: 5
top_k_compare: 3

# Hybrid retrieval (BM25 + Reciprocal Rank Fusion)
use_bm25: true
rrf_k: 60
keyword_candidates: 50

# Keyword backend: "elasticsearch" (CDC-synced, pre-filter) hoặc "memory"
# (fallback BM25 in-memory). Tự fallback sang memory nếu ES down.
keyword_backend: "elasticsearch"
es_url: "http://localhost:9200"          # override bằng ELASTICSEARCH_URL
es_index: "product_chunks"

# CDC sync (Debezium -> Kafka -> sync workers)
kafka_bootstrap: "localhost:9092"                 # override bằng KAFKA_BOOTSTRAP_SERVERS
products_topic: "ragshop.public.product_catalog"
catalog_table: "product_catalog"                  # bảng source of truth
```

Cấu hình được nạp thành dataclass `PipelineConfig` qua `PipelineConfig.from_yaml()` và được inject vào các component thông qua các factory function trong `api/deps.py`.

## Nạp dữ liệu (Data Ingestion)

Trước khi chạy server, khởi động Postgres rồi nạp dữ liệu sản phẩm:

```bash
# Khởi động Postgres với pgvector (Docker)
cd docker && docker compose up -d postgres && cd ..

# Sinh dữ liệu mẫu (tạo các file JSON trong data/raw/products/)
uv run python scripts/seed.py

# Ingest — chế độ mặc định ghi catalog + pgvector + Elasticsearch
uv run python scripts/ingest.py

# Hoặc chỉ catalog: chỉ ghi product_catalog và để các sync worker CDC
# xây cả hai index từ Debezium initial snapshot
uv run python scripts/ingest.py --catalog-only
```

Chế độ mặc định sẽ:

1. Load dữ liệu sản phẩm từ `data/raw/products/`
2. Làm sạch và chuẩn hóa dữ liệu
3. Chia nhỏ các trường sản phẩm (chunk)
4. Sinh embedding qua Gemini
5. Ghi bảng `product_catalog` (source of truth)
6. Lưu vector vào bảng `products` trong Postgres (pgvector, chỉ mục HNSW cosine)
7. Bulk-upsert index keyword vào Elasticsearch (bỏ qua nếu ES không kết nối được)

Cờ `--catalog-only` chỉ ghi `product_catalog`; các sync worker đang chạy sau đó tự xây cả hai index dẫn xuất từ CDC snapshot. Lưu ý bảng source of truth là `product_catalog`, còn bảng lưu vector là `products`.

### Chạy các CDC Sync Worker (không dùng Docker)

Hai sync worker giữ các index dẫn xuất luôn fresh từ change stream của Debezium. Trong Docker chúng chạy tự động dưới dạng service **indexer-worker** và **embedding-worker**; để chạy cục bộ không dùng Docker:

```bash
# Indexer worker → index keyword Elasticsearch
uv run python scripts/sync_worker.py --role indexer

# Embedding worker → pgvector (chỉ re-embed khi text thay đổi)
uv run python scripts/sync_worker.py --role embedder
```

Cả hai đều yêu cầu Kafka, Elasticsearch, và Postgres phải kết nối được, và Debezium connector đã được đăng ký (service `connect-init` làm việc này trong Docker).

## Chạy API Server

```bash
uv run uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

Server khởi động tại `http://localhost:8000`. Các endpoint chính:

| Method              | Endpoint         | Mô tả                              |
| ------------------- | ---------------- | ---------------------------------- |
| POST                | `/api/recommend` | Gợi ý sản phẩm                      |
| POST                | `/api/compare`   | So sánh sản phẩm                   |
| POST                | `/api/search`    | Tìm kiếm sản phẩm                  |
| GET/POST/PUT/DELETE | `/api/products`  | CRUD catalog (source of truth)     |
| GET                 | `/health`        | Kiểm tra tình trạng (health check) |

Tài liệu API tương tác có sẵn tại `http://localhost:8000/docs` (Swagger UI).

### Ví dụ Request

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Điện thoại chụp ảnh đẹp dưới 15 triệu", "top_k": 3}'
```

## Chạy Tests

```bash
# Chạy toàn bộ test
uv run pytest tests/ -v

# Chỉ chạy unit test
uv run pytest tests/unit/ -v

# Chỉ chạy integration test
uv run pytest tests/integration/ -v

# Chạy kèm coverage
uv run pytest tests/ --cov=src --cov=api
```

!!! note
    Để dùng `--cov`, cần cài `pytest-cov` trước: `uv add --group dev pytest-cov`

## Docker

Dự án bao gồm cấu hình Docker Compose chạy toàn bộ stack CDC:

```bash
cd docker
docker compose up --build
```

Lệnh này khởi động:

- **app** — FastAPI server trên cổng `8000`
- **postgres** — Postgres + pgvector (catalog source of truth + vector), `wal_level=logical` cho CDC
- **redis** — Redis cache trên cổng `6379`
- **elasticsearch** — index keyword BM25 (`product_chunks`) trên cổng `9200`
- **kafka** — event stream single-node KRaft trên cổng `9092`
- **connect** — Debezium (Kafka Connect) trên cổng `8083`
- **connect-init** — job chạy một lần: đăng ký Debezium connector rồi thoát
- **indexer-worker** — CDC consumer → Elasticsearch
- **embedding-worker** — CDC consumer → pgvector

Xem [hướng dẫn triển khai Docker](../deployment/docker.vi.md) để biết về volume, các lệnh vòng đời, và image GHCR có sẵn. Thư mục `data/` được mount như một volume và vector được persist trong named volume `pgdata` qua các lần restart container.

### Chỉ Build Image

```bash
docker build -f docker/Dockerfile -t rag-product-recommend .
```

## Chạy Docs cục bộ

```bash
uv run mkdocs serve
```

Mở tại `http://localhost:8000` (hoặc `8001` nếu `8000` đã được dùng). Các thay đổi trong `docs/` sẽ tự động hot-reload.

## Tổng hợp các lệnh thường dùng

| Lệnh | Mô tả |
| ------- | ----------- |
| `uv sync` | Cài đặt/cập nhật toàn bộ dependencies |
| `uv add <pkg>` | Thêm một production dependency |
| `uv add --group dev <pkg>` | Thêm một dev dependency |
| `uv run <cmd>` | Chạy lệnh bên trong venv |
| `uv run pytest tests/ -v` | Chạy test |
| `uv run uvicorn api.app:app --reload` | Khởi động dev server |
| `uv run mkdocs serve` | Chạy docs cục bộ |
| `uv run mkdocs build --strict` | Build docs (chế độ CI) |

## Quản lý Dependencies

Dự án này dùng **uv** với `pyproject.toml` (tương tự `package.json` trong Node.js). File lockfile `uv.lock` ghim chính xác version (tương tự `package-lock.json`).

- **Production deps** — liệt kê dưới `[project] dependencies`
- **Dev deps** — dưới `[dependency-groups] dev` (pytest, ...)
- **Docs deps** — dưới `[dependency-groups] docs` (mkdocs-material, ...)

Không bao giờ cài package bằng `pip install` trực tiếp. Luôn dùng `uv add`.
