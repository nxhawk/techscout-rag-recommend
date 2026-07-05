# Triển khai với Docker

Hướng dẫn này bao gồm hai cách chạy dự án với Docker: build cục bộ bằng Docker Compose, hoặc pull image đã build sẵn từ GitHub Container Registry (GHCR).

## Cách 1 — Docker Compose (Build cục bộ)

Phù hợp nhất cho phát triển cục bộ. Build image từ source và khởi động API server cùng Postgres (pgvector) và Redis.

### Yêu cầu

- Docker Engine 20.10+
- Docker Compose v2

### Chạy

```bash
# 1. Cấu hình biến môi trường
cp .env.example .env
# Chỉnh sửa .env với API key của bạn

# 2. Khởi động tất cả service
cd docker
docker compose up --build
```

Lệnh này khởi động toàn bộ stack CDC:

| Service | Port | Mô tả |
| ------- | ---- | ----------- |
| **app** | `8000` | FastAPI server (keyword backend: Elasticsearch) |
| **postgres** | `5432` | Postgres + pgvector — catalog (source of truth) + vectors; `wal_level=logical` cho CDC |
| **elasticsearch** | `9200` | Index keyword/BM25 (`product_chunks`) |
| **kafka** | — | Event stream (KRaft single-node) |
| **connect** | `8083` | Debezium (Kafka Connect) — bắt thay đổi bảng `product_catalog` |
| **connect-init** | — | Chạy một lần: đăng ký Debezium connector (`docker/debezium/`) rồi thoát |
| **indexer-worker** | — | CDC consumer → Elasticsearch |
| **embedding-worker** | — | CDC consumer → pgvector (chỉ re-embed khi text đổi) |
| **redis** | `6379` | Redis cache |

Tạo/cập nhật/xóa sản phẩm qua `POST/PUT/DELETE /api/products` tự lan truyền
sang cả hai index tìm kiếm (xem
[Truy xuất lai](../architecture/hybrid-retrieval.md)).

API có sẵn tại `http://localhost:8000`. Tài liệu tương tác tại `http://localhost:8000/docs`.

### Dừng

```bash
docker compose down

# Xóa cả volume (xóa dữ liệu đã cache)
docker compose down -v
```

### Rebuild sau khi đổi code

```bash
docker compose up --build
```

Docker layer caching có nghĩa là chỉ layer thay đổi mới được rebuild. Thay đổi dependency (sửa `pyproject.toml`) kích hoạt cài đặt lại toàn bộ; thay đổi chỉ ở code thì nhanh hơn nhiều.

### Lưu trữ dữ liệu bền vững

Vector được lưu trong Postgres, persist qua named volume `pgdata`. Thư mục `data/` vẫn được mount cho dữ liệu sản phẩm thô:

```yaml
volumes:
  - ../data:/app/data   # dữ liệu thô (service app)
  - pgdata:/var/lib/postgresql/data   # vector (service postgres)
```

Nếu cần một vector store sạch, xóa volume và chạy lại ingestion:

```bash
docker compose down -v   # xóa pgdata
docker compose up -d
docker compose exec app uv run python scripts/ingest.py
```

---

## Cách 2 — Image GHCR có sẵn

Phù hợp nhất cho triển khai hoặc test nhanh mà không cần clone repo. Mỗi lần push lên `main` và mỗi version tag đều tự động build và push image lên GitHub Container Registry.

### Các Tag có sẵn

| Tag | Mô tả | Ví dụ |
| --- | ----------- | ------- |
| `main` | Commit mới nhất trên branch `main` | `ghcr.io/nxhawk/rag-product-recommend:main` |
| `v*.*.*` | Bản phát hành theo semantic version | `ghcr.io/nxhawk/rag-product-recommend:v1.0.0` |
| `v*.*` | Major.minor (rolling) | `ghcr.io/nxhawk/rag-product-recommend:v1.0` |
| `<sha>` | SHA commit cụ thể | `ghcr.io/nxhawk/rag-product-recommend:a1b2c3d` |

### Pull & Chạy

```bash
# Pull image mới nhất
docker pull ghcr.io/nxhawk/rag-product-recommend:main

# Chạy kèm biến môi trường
docker run -d \
  --name rag-api \
  -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENAI_API_KEY=sk-... \
  -e ENVIRONMENT=production \
  -v $(pwd)/data:/app/data \
  ghcr.io/nxhawk/rag-product-recommend:main
```

### Chạy với file `.env`

```bash
docker run -d \
  --name rag-api \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/nxhawk/rag-product-recommend:main
```

### Chạy kèm Redis (Docker Compose)

Tạo một file `docker-compose.prod.yml`:

```yaml
version: "3.8"

services:
  app:
    image: ghcr.io/nxhawk/rag-product-recommend:main
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/rag_products
    volumes:
      - ./data:/app/data
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: rag_products
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d rag_products"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

volumes:
  pgdata:
```

```bash
docker compose -f docker-compose.prod.yml up -d
```

---

## Biến môi trường

Các biến này cần được thiết lập qua `--env-file`, cờ `-e`, hoặc trong file `.env`:

| Biến | Bắt buộc | Mô tả |
| -------- | -------- | ----------- |
| `ANTHROPIC_API_KEY` | Có* | API key của Anthropic Claude |
| `OPENAI_API_KEY` | Có* | API key của OpenAI (dùng cho embedding) |
| `GEMINI_API_KEY` | Không | API key của Google Gemini |
| `DATABASE_URL` | Không | Chuỗi kết nối Postgres (mặc định: `postgresql://postgres:postgres@localhost:5432/rag_products`; Docker Compose tự thiết lập) |
| `ENVIRONMENT` | Không | `development` (mặc định) hoặc `production` |
| `LOG_LEVEL` | Không | `DEBUG`, `INFO` (mặc định), `WARNING`, `ERROR` |

*Tối thiểu bạn cần key cho LLM provider đã cấu hình (`ANTHROPIC_API_KEY` theo mặc định) và `OPENAI_API_KEY` cho embedding.

---

## Nạp dữ liệu trong Docker

Container không tự động nạp dữ liệu. Bạn cần chạy ingestion thủ công:

```bash
# Nếu chạy với docker compose
docker compose exec app uv run python scripts/seed.py
docker compose exec app uv run python scripts/ingest.py

# Nếu chạy container độc lập
docker exec rag-api uv run python scripts/seed.py
docker exec rag-api uv run python scripts/ingest.py
```

Sau khi ingest, vector được lưu trong Postgres (volume `pgdata`) và vẫn tồn tại qua các lần restart.

---

## Health Check

Kiểm tra server đang chạy:

```bash
curl http://localhost:8000/health
```

Test một request gợi ý:

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Điện thoại chụp ảnh đẹp dưới 15 triệu", "top_k": 3}'
```

---

## Các lệnh hữu ích

```bash
# Xem log
docker compose logs -f app

# Vào shell của container
docker compose exec app bash

# Kiểm tra kích thước image
docker images ghcr.io/nxhawk/rag-product-recommend

# Xóa image cũ
docker image prune -f
```

---

## CI/CD Pipeline

Image GHCR được build tự động bởi GitHub Actions (`.github/workflows/docker.yml`):

1. **Test** — cài dependency, chạy `pytest tests/ -v`
2. **Build & Push** — chỉ khi test pass; chỉ push trên branch `main` và tag (PR chỉ build, không push)

Để kích hoạt một bản phát hành có version, tạo git tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Lệnh này tạo ra các image được gắn tag `v1.0.0`, `v1.0`, và commit SHA.
