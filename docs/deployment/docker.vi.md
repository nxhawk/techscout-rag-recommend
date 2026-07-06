# Triển khai với Docker

Repository cung cấp một stack **Docker Compose** đầy đủ, chạy toàn bộ kiến trúc
CDC chỉ với một lệnh: API, cả hai datastore (Postgres + pgvector và
Elasticsearch), pipeline change-data-capture Kafka + Debezium, hai sync worker,
Redis, **Kibana** để xem dữ liệu Elasticsearch, **Kafka UI** để xem các topic
Kafka và Debezium connector, cùng một stack **Prometheus + Grafana** (kèm exporter
cho từng datastore) để thu thập metric và dashboard — xem [Giám sát](monitoring.md).

Có hai cách chạy dự án:

- **Cách 1 — Docker Compose (full stack)** — khuyến nghị cho phát triển local. Mọi thứ được nối sẵn, nên thay đổi sản phẩm sẽ tự chảy qua CDC tới cả hai index tìm kiếm.
- **Cách 2 — Image dựng sẵn trên GHCR (tối giản)** — bản triển khai nhẹ chỉ gồm API + Postgres + Redis, không có Elasticsearch/Kafka (nhánh keyword tự fallback về BM25 in-memory).

## Kiến trúc stack

Stack Compose là bản hiện thực tham chiếu của
[luồng dữ liệu](../architecture/data-flow.vi.md) hệ thống: bảng
`product_catalog` là source of truth duy nhất, và mọi thay đổi đều được pipeline
CDC lan truyền tới hai index tìm kiếm dẫn xuất.

```mermaid
flowchart LR
    U["localhost:8000\nAPI"] --> APP["app\n(FastAPI)"]
    KB["localhost:5601\nKibana"] --> ES
    KUI["localhost:8080\nKafka UI"] --> KF
    KUI --> CN

    APP -->|"ghi CRUD"| PG[("postgres\nproduct_catalog + products/pgvector")]
    APP -->|"semantic search"| PG
    APP -->|"keyword search"| ES[("elasticsearch\nproduct_chunks")]
    APP -.->|"cache"| RD["redis"]

    PG -->|"WAL (logical)"| CN["connect\n(Debezium)"]
    CN -->|"change events"| KF["kafka\nragshop.public.product_catalog"]
    KF --> IW["indexer-worker"]
    KF --> EW["embedding-worker"]
    IW --> ES
    EW --> PG
```

`postgres` đảm nhận hai vai trò: chứa bảng `product_catalog` (**nguồn** của CDC)
và bảng `products` + pgvector (index semantic, **đích** của CDC). Debezium chỉ
capture `product_catalog`, nên việc embedding worker ghi vector ngược lại vào
`products` không bao giờ tạo vòng lặp.

---

## Cách 1 — Docker Compose (Full Stack)

### Yêu cầu

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`, không phải `docker-compose` cũ)
- ~4 GB RAM trống (Elasticsearch, Kafka và Postgres đều ngốn bộ nhớ)
- API key cho provider đang cấu hình (mặc định là Gemini)

### 1. Cấu hình biến môi trường

Tạo file `.env` ở **thư mục gốc repository** (repo không kèm sẵn
`.env.example`). Service `app` và `embedding-worker` đọc nó qua
`env_file: ../.env`:

```dotenv
# Provider mặc định là Gemini (dùng cho cả LLM và embedding)
GEMINI_API_KEY=AIza...

# Tùy chọn — chỉ khi bạn đổi provider trong configs/settings.yaml
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

Compose tự inject các biến kết nối hạ tầng (`DATABASE_URL`, `ELASTICSEARCH_URL`,
`KAFKA_BOOTSTRAP_SERVERS`, `KEYWORD_BACKEND`) — bạn **không** cần đặt chúng trong
`.env`.

### 2. Khởi động stack

```bash
cd docker
docker compose up --build -d
```

Lần chạy đầu sẽ build image app và pull các image Elasticsearch, Kafka, Kibana,
Kafka UI, Debezium (vài GB), nên hãy đợi 1–2 phút. Compose chặn khởi động theo health
check (xem bên dưới), và `connect-init` đăng ký Debezium connector khi mọi thứ
đã sẵn sàng.

### Các service

| Service | Image | Cổng host | Phụ thuộc (healthy) | Vai trò |
| ------- | ----- | --------- | ------------------- | ------- |
| **app** | build từ `docker/Dockerfile` | `8000` | postgres, elasticsearch, redis | FastAPI server; `KEYWORD_BACKEND=elasticsearch` |
| **postgres** | `pgvector/pgvector:pg16` | `5432` | — | Catalog (source of truth) + pgvector; chạy với `wal_level=logical` cho CDC |
| **elasticsearch** | `docker.elastic.co/elasticsearch/elasticsearch:8.14.3` | `9200` | — | Index keyword/BM25 `product_chunks` (đã tắt security, single-node) |
| **kibana** | `docker.elastic.co/kibana/kibana:8.14.3` | `5601` | elasticsearch | Web UI để xem/query Elasticsearch |
| **kafka** | `apache/kafka:3.7.2` | — (`9092` nội bộ) | — | Event stream, single-node KRaft (không ZooKeeper) |
| **kafka-ui** | `kafbat/kafka-ui:v1.4.2` | `8080` | kafka, connect | Web UI xem topic/message Kafka, consumer lag và Debezium connector |
| **connect** | `debezium/connect:2.7.3.Final` | `8083` | kafka, postgres | Kafka Connect chạy Debezium Postgres connector |
| **connect-init** | `curlimages/curl:8.8.0` | — | connect | One-shot: `PUT` cấu hình connector từ `docker/debezium/` rồi thoát |
| **indexer-worker** | build từ `docker/Dockerfile` | — | kafka, elasticsearch | `sync_worker.py --role indexer` → Elasticsearch; chờ ES lúc khởi động, healthcheck bằng heartbeat |
| **embedding-worker** | build từ `docker/Dockerfile` | — | kafka, postgres | `sync_worker.py --role embedder` → pgvector (chỉ re-embed khi text đổi); chờ Postgres lúc khởi động, healthcheck bằng heartbeat |
| **redis** | `redis:7-alpine` | `6379` | — | Cache |
| **prometheus** | `prom/prometheus:v2.53.1` | `9090` | app | Scrape `/metrics` từ app + exporter; kho time-series ([Giám sát](monitoring.md)) |
| **grafana** | `grafana/grafana:11.1.0` | `3000` | prometheus | Dashboard trên nền Prometheus; datasource + board **RAG - Overview** provision sẵn |
| **postgres-exporter** | `quay.io/prometheuscommunity/postgres-exporter:v0.15.0` | `9187` | postgres | Metric Postgres cho Prometheus |
| **redis-exporter** | `oliver006/redis_exporter:v1.62.0` | `9121` | redis | Metric Redis cho Prometheus |
| **elasticsearch-exporter** | `quay.io/prometheuscommunity/elasticsearch-exporter:v1.7.0` | `9114` | elasticsearch | Metric Elasticsearch cho Prometheus |
| **kafka-exporter** | `danielqsj/kafka-exporter:v1.7.0` | `9308` | kafka | **Lag** consumer-group + offset Kafka (độ mới CDC) |

### Thứ tự khởi động & health gating

Compose không khởi động một service cho tới khi các phụ thuộc báo **healthy**:

- `postgres`, `elasticsearch` và `kafka` có health check; mọi service nói chuyện với chúng đều đợi (`depends_on: condition: service_healthy`).
- `connect-init` đợi `connect` healthy, `PUT`
  `docker/debezium/product-catalog-connector.json` tới
  `http://connect:8083/connectors/product-catalog-connector/config`
  (idempotent — an toàn ở mỗi lần `up`), in xác nhận, rồi thoát với `restart: "no"`.
- `indexer-worker` và `embedding-worker` chạy với `restart: unless-stopped`; lần đầu khởi động chúng consume **initial snapshot** của Debezium (`auto.offset.reset=earliest`) — đó là cách một index mới được bootstrap.
- **Khởi động worker có khả năng chịu lỗi.** Ngoài `depends_on`, mỗi worker còn *chờ* datastore của mình trước khi consume: `ESKeywordSearch.setup()` và `VectorStore.setup()` retry với exponential backoff (tối đa ~30 lần, 1→5 s) thay vì crash nếu Elasticsearch/Postgres tạm thời chưa lên. Mỗi worker cũng ghi một file heartbeat (`WORKER_HEARTBEAT_FILE`, mặc định `/tmp/worker.heartbeat`) mỗi vòng poll, và `healthcheck` của Compose đánh dấu unhealthy khi file đó cũ quá (>30 s). Nhờ vậy `docker compose ps` chỉ ra worker thực sự treo/chết, còn worker chỉ đang chờ topic xuất hiện vẫn **healthy**.
- `app` chỉ phụ thuộc `postgres`, `elasticsearch` và `redis` — không phụ thuộc Kafka/Connect — nên API có thể phục vụ đọc trong khi pipeline CDC còn đang khởi động.

### 3. Nạp dữ liệu (lần đầu)

Stack **không** tự nạp dữ liệu. Seed catalog và index một lần khi các service đã
lên:

```bash
# Ghi cả ba đích: product_catalog + pgvector + Elasticsearch
docker compose exec app uv run python scripts/ingest.py

# Cách khác: chỉ ghi catalog source-of-truth và để CDC worker
# tự dựng cả hai index từ Debezium snapshot
docker compose exec app uv run python scripts/ingest.py --catalog-only
```

Sau đó, các thay đổi qua `POST/PUT/DELETE /api/products` sẽ tự lan truyền tới cả
hai index qua CDC — xem
[Truy xuất lai](../architecture/hybrid-retrieval.vi.md)
và [sync_worker.py](../scripts/sync-worker.vi.md).

### 4. Kiểm tra mọi thứ đã nối đúng

```bash
# API đã lên chưa?
curl http://localhost:8000/health

# Một request gợi ý (cần đã nạp dữ liệu + có provider key)
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Điện thoại chụp ảnh đẹp dưới 15 triệu", "top_k": 3}'

# Debezium connector đã đăng ký & đang chạy?
curl http://localhost:8083/connectors/product-catalog-connector/status

# Index keyword Elasticsearch đã có dữ liệu?
curl "http://localhost:9200/product_chunks/_count?pretty"
```

API ở `http://localhost:8000` (docs tương tác ở `http://localhost:8000/docs`);
Kibana ở `http://localhost:5601`; Kafka UI ở `http://localhost:8080`.

---

## Quản lý stack

### Khởi động / dừng một phần

```bash
docker compose up -d postgres elasticsearch kafka   # chỉ hạ tầng
docker compose up -d kibana                          # thêm Kibana sau
docker compose up -d kafka-ui                         # thêm Kafka UI sau
docker compose up -d prometheus grafana \
  postgres-exporter redis-exporter \
  elasticsearch-exporter kafka-exporter               # thêm stack giám sát
docker compose stop indexer-worker embedding-worker  # tạm dừng CDC worker
docker compose restart connect-init                  # đăng ký lại connector
```

### Logs

```bash
docker compose logs -f app                # API
docker compose logs -f embedding-worker   # CDC → pgvector
docker compose logs -f indexer-worker     # CDC → Elasticsearch
docker compose logs -f connect            # Debezium
docker compose logs connect-init          # kết quả đăng ký connector
```

### Rebuild sau khi đổi code

```bash
docker compose up --build -d
```

Docker layer caching nghĩa là chỉ layer thay đổi mới build lại. Sửa
`pyproject.toml` sẽ kích hoạt cài lại toàn bộ dependency; đổi code thuần thì
nhanh.

### Dừng & reset

```bash
docker compose down          # dừng, giữ volume dữ liệu
docker compose down -v       # xóa luôn volume (pgdata, esdata, kafkadata)
```

Xóa volume sẽ wipe catalog, vector, index Elasticsearch **và** log Kafka (gồm cả
Debezium offset), nên lần `up` + `ingest` kế tiếp bắt đầu hoàn toàn sạch.

### Xóa dữ liệu & nạp lại (giữ nguyên stack)

Muốn wipe dữ liệu sản phẩm và làm lại từ đầu **mà không** tắt container (và không
mất log Kafka), hãy làm rỗng cả ba data store rồi chạy lại `ingest.py`. Ba store
gồm: catalog nguồn (`product_catalog`), bảng pgvector dẫn xuất (`products`), và
index keyword Elasticsearch (`product_chunks`):

```bash
# 1. Postgres — làm rỗng cả catalog nguồn LẪN bảng pgvector dẫn xuất
docker compose exec postgres psql -U postgres -d rag_products \
  -c "TRUNCATE product_catalog, products;"

# 2. Elasticsearch — xóa index keyword (báo 404 cũng không sao nếu index đã bị xóa)
curl -X DELETE "http://localhost:9200/product_chunks"

# 3. Nạp lại — ghi thẳng cả ba đích (catalog + pgvector + ES)
docker compose exec app uv run python scripts/ingest.py
```

`ingest.py` tự tạo lại index và cả hai bảng khi cần (`CREATE … IF NOT EXISTS`),
nên truncate/xóa trước là an toàn. Vì nó ghi thẳng vào pgvector và Elasticsearch,
bạn **không** phải đợi CDC worker dựng lại — các row catalog vừa chèn lại vẫn chảy
qua Debezium, nhưng embedding worker bỏ qua re-embedding nhờ `content_hash` của
từng chunk.

!!! warning "TRUNCATE không được CDC lan truyền — hãy tự xóa index"
    Sync worker chỉ áp dụng event mức row `c`/`u`/`d`/`r`; event **TRUNCATE** của
    Debezium bị bỏ qua. Nên chỉ truncate `product_catalog` sẽ **không** xóa
    `products` / `product_chunks` — bạn phải tự làm rỗng hai store đó (bước 1–2).
    Nếu muốn để CDC tự xóa giúp, hãy chạy `DELETE FROM product_catalog;` (không
    phải `TRUNCATE`): mỗi row phát ra một event `d` mà worker tự lan truyền tới cả
    hai index (chậm hơn nếu catalog lớn, và cần worker đang chạy).

Muốn *sạch hoàn toàn* — gồm cả log Kafka và Debezium offset — dùng
`docker compose down -v` (ở trên) rồi `up` + `ingest`.

---

## Xem dữ liệu

### Elasticsearch — Kibana

Xem **[Xem dữ liệu trong Kibana](kibana.vi.md)** để có hướng dẫn đầy đủ (query
Dev Tools, Discover data view, bộ lọc KQL, tham chiếu field). Bản nhanh — mở
`http://localhost:5601`:

- **Dev Tools** (Management → Dev Tools) để query trực tiếp:

  ```
  GET product_chunks/_search
  { "query": { "match_all": {} }, "size": 5 }
  ```

- **Discover** để xem dạng grid: tạo **Data View** với pattern `product_chunks`,
  ở bước chọn time field chọn *"I don't want to use the time filter"* (index này
  không có trường thời gian).

Hoặc gọi thẳng REST API:

```bash
curl "http://localhost:9200/_cat/indices?v"
curl "http://localhost:9200/product_chunks/_search?pretty&size=3"
```

### Postgres — psql

```bash
# Catalog source-of-truth
docker compose exec postgres psql -U postgres -d rag_products \
  -c "SELECT product_id, name, price FROM product_catalog LIMIT 5;"

# Index semantic dẫn xuất (các row chunk + metadata)
docker compose exec postgres psql -U postgres -d rag_products \
  -c "SELECT id, metadata->>'chunk_type' AS type FROM products LIMIT 5;"
```

### Kafka — Kafka UI

Muốn xem topic, message trực tiếp, consumer-group lag và Debezium connector theo
kiểu bấm-chuột, mở **[Kafka UI](kafka-ui.vi.md)** ở `http://localhost:8080` (không
cần đăng nhập). Đây là "Kibana cho Kafka" trong stack này — xem trang riêng để có
hướng dẫn chi tiết.

### Kafka — topic & consumer lag

Cùng thông tin đó cũng lấy được từ CLI:

```bash
# Liệt kê topic (topic CDC là ragshop.public.product_catalog)
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Consumer group (mỗi sync worker một group: rag-sync-indexer, rag-sync-embedder)
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group rag-sync-embedder
```

Cột `LAG` trong output `--describe` cho biết worker đang trễ bao nhiêu — đúng
bằng cửa sổ eventual-consistency giữa lúc ghi catalog và lúc index tìm kiếm bắt
kịp.

### Debezium — trạng thái connector

```bash
curl http://localhost:8083/connectors                                   # liệt kê
curl http://localhost:8083/connectors/product-catalog-connector/status  # trạng thái + task
```

### Metric & dashboard — Prometheus & Grafana

Để xem request rate, độ trễ, tỉ lệ lỗi, lỗi hết quota LLM và lag CDC **theo thời
gian**, mở Grafana tại `http://localhost:3000` (admin / admin) — dashboard
**RAG - Overview** đã được provision sẵn. Prometheus ở `http://localhost:9090`
(**Status → Targets** cho biết đang scrape những gì). App tự expose metric tại
`http://localhost:8000/metrics`. Xem **[Giám sát](monitoring.md)** để biết toàn bộ
luồng, danh sách metric và các truy vấn dashboard.

---

## Biến môi trường

Đặt qua `.env` (gốc repo), `--env-file`, hoặc cờ `-e`. Trong full stack Compose,
các biến hạ tầng đã được đặt sẵn cho bạn.

| Biến | Bắt buộc | Mô tả |
| ---- | -------- | ----- |
| `GEMINI_API_KEY` | Có* | Key Google Gemini — provider mặc định cho **cả** LLM và embedding |
| `ANTHROPIC_API_KEY` | Không | Chỉ khi `llm_provider: anthropic` trong `configs/settings.yaml` |
| `OPENAI_API_KEY` | Không | Chỉ khi đổi provider LLM/embedding sang OpenAI |
| `DATABASE_URL` | Auto | DSN Postgres; Compose đặt thành `postgresql://postgres:postgres@postgres:5432/rag_products` |
| `ELASTICSEARCH_URL` | Auto | Compose đặt thành `http://elasticsearch:9200` |
| `KAFKA_BOOTSTRAP_SERVERS` | Auto | Compose đặt thành `kafka:9092` (cho sync worker) |
| `WORKER_HEARTBEAT_FILE` | Auto | Compose đặt (`/tmp/worker.heartbeat`) cho sync worker — file mỗi worker touch mỗi vòng poll và healthcheck theo dõi. Không đặt = tắt heartbeat |
| `KEYWORD_BACKEND` | Auto | `elasticsearch` trong Compose; fallback về BM25 in-memory nếu ES không truy cập được |
| `ENVIRONMENT` | Không | `development` (mặc định) hoặc `production` |
| `LOG_LEVEL` | Không | `DEBUG`, `INFO` (mặc định), `WARNING`, `ERROR` |

*Bạn chỉ cần key cho provider được chọn trong `configs/settings.yaml` (mặc định
Gemini). Hỗ trợ nhiều key để xoay vòng (`GEMINI_API_KEY=key_a,key_b`).

## Tham chiếu cổng & volume

| Cổng host | Service | Dùng để |
| --------- | ------- | ------- |
| `8000` | app | REST API + Swagger UI |
| `5601` | kibana | UI Elasticsearch |
| `8080` | kafka-ui | Kafka UI (topic, message, consumer lag, connector) |
| `9200` | elasticsearch | REST API của ES |
| `5432` | postgres | Truy cập SQL (psql / DBeaver) |
| `8083` | connect | REST Kafka Connect / Debezium |
| `6379` | redis | Cache |
| `3000` | grafana | Dashboard (admin / admin) |
| `9090` | prometheus | Giao diện truy vấn + trạng thái scrape target |
| `9187` | postgres-exporter | Metric Postgres |
| `9121` | redis-exporter | Metric Redis |
| `9114` | elasticsearch-exporter | Metric Elasticsearch |
| `9308` | kafka-exporter | Metric lag/offset Kafka |

`app` cũng tự expose metric Prometheus tại `http://localhost:8000/metrics`.

| Volume | Service | Nội dung |
| ------ | ------- | -------- |
| `pgdata` | postgres | `product_catalog` + `products`/pgvector |
| `esdata` | elasticsearch | Index keyword `product_chunks` |
| `kafkadata` | kafka | Event log + Debezium offset |
| `promdata` | prometheus | Lịch sử time-series đã scrape |
| `grafanadata` | grafana | Trạng thái Grafana (chỉnh sửa dashboard, tùy chọn) |

---

## Cách 2 — Image dựng sẵn trên GHCR (tối giản)

Phù hợp để triển khai nhanh hoặc thử nghiệm mà không cần clone repo. Mỗi push lên
`main` và mỗi version tag đều build và push image lên GitHub Container Registry.

!!! warning "Đây là bản triển khai tối giản"
    Ví dụ dưới chỉ chạy **app + Postgres + Redis** — không có Elasticsearch,
    Kafka hay Debezium. Ở chế độ này nhánh keyword dùng snapshot BM25 in-memory
    (dựng lúc khởi động) và **không có CDC**, nên thay đổi catalog chỉ được phản
    ánh sau khi re-ingest. Muốn hành vi hybrid + đồng bộ thời gian thực đầy đủ,
    dùng Cách 1.

### Các tag có sẵn

| Tag | Mô tả | Ví dụ |
| --- | ----- | ----- |
| `main` | Commit mới nhất trên `main` | `ghcr.io/nxhawk/rag-product-recommend:main` |
| `v*.*.*` | Bản release theo semantic version | `ghcr.io/nxhawk/rag-product-recommend:v1.0.0` |
| `v*.*` | Major.minor (rolling) | `ghcr.io/nxhawk/rag-product-recommend:v1.0` |
| `<sha>` | Commit SHA cụ thể | `ghcr.io/nxhawk/rag-product-recommend:a1b2c3d` |

### Pull & chạy

```bash
docker pull ghcr.io/nxhawk/rag-product-recommend:main

docker run -d \
  --name rag-api \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/nxhawk/rag-product-recommend:main
```

### Compose tối giản (app + Postgres + Redis)

```yaml
services:
  app:
    image: ghcr.io/nxhawk/rag-product-recommend:main
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://postgres:postgres@postgres:5432/rag_products
      KEYWORD_BACKEND: memory   # không có Elasticsearch trong stack tối giản
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
docker compose -f docker-compose.prod.yml exec app uv run python scripts/ingest.py
```

---

## Xử lý sự cố

| Triệu chứng | Nguyên nhân & cách xử lý |
| ----------- | ------------------------ |
| `app` trả `503` ở `/api/recommend` | Chưa nạp dữ liệu, hoặc provider API key thiếu/sai. Chạy `ingest.py` và kiểm tra `.env`. |
| Gợi ý chạy được nhưng kết quả keyword yếu | Elasticsearch không truy cập được → API âm thầm fallback về BM25 in-memory. Xem `docker compose logs elasticsearch` và `curl localhost:9200/_cluster/health`. |
| `connect-init` thoát mà không đăng ký | `connect` chưa healthy. Chạy lại `docker compose up -d --force-recreate connect-init` và xem `docker compose logs connect-init`. |
| `.../connectors/product-catalog-connector/status` trả `404 No status found` | Debezium connector chưa được đăng ký, nên topic `ragshop.public.product_catalog` không được tạo và **cả hai** index đều rỗng. Đăng ký lại: `docker compose up -d --force-recreate connect-init` (hoặc `PUT` config bằng tay) rồi kiểm tra lại status. |
| Ghi catalog không xuất hiện trong tìm kiếm | Một sync worker chết hoặc đang trễ. Xem `docker compose logs embedding-worker indexer-worker` và cột `LAG` của consumer-group (xem trên). |
| Elasticsearch có data nhưng pgvector (`products`) rỗng | Chỉ nhánh **embedding** hỏng — thường do thiếu/sai `GEMINI_API_KEY` (indexer không cần key). Xem `docker compose logs embedding-worker`; thêm key vào `.env` rồi `docker compose up -d --force-recreate embedding-worker`. |
| Một worker cứ restart ngay sau khi khởi động | Nó không nối được datastore. Worker giờ retry với backoff nên sẽ tự lành khi Postgres/Elasticsearch lên; nếu vẫn lặp thì dependency thực sự đang down hoặc khác network — xem `docker compose ps` và log service đó. |
| Container Elasticsearch cứ restart | Thiếu bộ nhớ. Nó bị ghim `-Xms512m -Xmx512m`; cấp thêm RAM cho Docker hoặc giảm `ES_JAVA_OPTS`. |
| Kafka UI không thấy cluster / báo "offline" | Broker chưa sẵn sàng lúc khởi động, hoặc `KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS` sai. Xem `docker compose logs kafka-ui` và kiểm tra `kafka` đã healthy chưa. |
| Cổng đã bị chiếm | Tiến trình khác đang giữ `8000/5432/9200/5601/8080/8083/6379`. Dừng nó hoặc đổi mapping `ports:`. |

---

## Pipeline CI/CD

Image GHCR được build tự động bởi GitHub Actions
(`.github/workflows/docker.yml`):

1. **Test** — cài deps, chạy `pytest tests/ -v`.
2. **Build & Push** — chỉ khi test pass; push trên `main` và tag (PR có build nhưng không push).

Để kích hoạt một bản release có version, tạo git tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Lệnh này tạo image tag `v1.0.0`, `v1.0`, và commit SHA.
