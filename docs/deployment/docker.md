# Docker Deployment

The repository ships a full **Docker Compose** stack that runs the entire CDC
architecture with a single command: the API, both datastores (Postgres +
pgvector and Elasticsearch), the Kafka + Debezium change-data-capture pipeline,
the two sync workers, Redis, **Kibana** for inspecting Elasticsearch,
**Kafka UI** for inspecting the Kafka topics and Debezium connector, and a
**Prometheus + Grafana** stack (with per-datastore exporters) for metrics and
dashboards — see [Monitoring](monitoring.md).

There are two ways to run the project:

- **Option 1 — Docker Compose (full stack)** — recommended for local development. Everything is wired together, so product writes flow through CDC to both search indexes automatically.
- **Option 2 — Pre-built GHCR image (minimal)** — a lightweight API + Postgres + Redis deployment without Elasticsearch/Kafka (keyword search falls back to the in-memory BM25 index).

## Stack Architecture

The Compose stack is the reference implementation of the system's
[data flow](../architecture/data-flow.md): the `product_catalog` table is the
single source of truth, and every write is propagated to the two derived search
indexes by the CDC pipeline.

```mermaid
flowchart LR
    U["localhost:8000\nAPI"] --> APP["app\n(FastAPI)"]
    KB["localhost:5601\nKibana"] --> ES
    KUI["localhost:8080\nKafka UI"] --> KF
    KUI --> CN

    APP -->|"CRUD write"| PG[("postgres\nproduct_catalog + products/pgvector")]
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

`postgres` plays two roles: it holds the `product_catalog` table (the CDC
**source**) and the `products` + pgvector table (the semantic index, a CDC
**sink**). Debezium only captures `product_catalog`, so the embedding worker
writing vectors back into `products` never creates a feedback loop.

---

## Option 1 — Docker Compose (Full Stack)

### Prerequisites

- Docker Engine 20.10+
- Docker Compose v2 (`docker compose`, not the legacy `docker-compose`)
- ~4 GB of free RAM (Elasticsearch, Kafka and Postgres together are memory-hungry)
- An API key for the configured provider (Gemini by default)

### 1. Configure environment

Create a `.env` file at the **repository root** (there is no committed
`.env.example`). The `app` and `embedding-worker` services read it via
`env_file: ../.env`:

```dotenv
# Default provider is Gemini (used for both LLM and embeddings)
GEMINI_API_KEY=AIza...

# Optional — only if you switch providers in configs/settings.yaml
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

The Compose file injects the infra connection variables (`DATABASE_URL`,
`ELASTICSEARCH_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `KEYWORD_BACKEND`) automatically
— you do **not** put those in `.env`.

### 2. Start the stack

```bash
cd docker
docker compose up --build -d
```

On the first run this builds the app image and pulls the Elasticsearch, Kafka,
Kibana, Kafka UI and Debezium images (a few GB), so allow 1–2 minutes. Compose gates
startup on health checks (see below), and `connect-init` registers the Debezium
connector once everything is ready.

### Services

| Service | Image | Host port | Depends on (healthy) | Role |
| ------- | ----- | --------- | -------------------- | ---- |
| **app** | built from `docker/Dockerfile` | `8000` | postgres, elasticsearch, redis | FastAPI server; `KEYWORD_BACKEND=elasticsearch` |
| **postgres** | `pgvector/pgvector:pg16` | `5432` | — | Catalog (source of truth) + pgvector; started with `wal_level=logical` for CDC |
| **elasticsearch** | `docker.elastic.co/elasticsearch/elasticsearch:8.14.3` | `9200` | — | Keyword/BM25 index `product_chunks` (security disabled, single-node) |
| **kibana** | `docker.elastic.co/kibana/kibana:8.14.3` | `5601` | elasticsearch | Web UI to browse/query Elasticsearch |
| **kafka** | `apache/kafka:3.7.2` | — (internal `9092`) | — | Event stream, single-node KRaft (no ZooKeeper) |
| **kafka-ui** | `kafbat/kafka-ui:v1.4.2` | `8080` | kafka, connect | Web UI to browse Kafka topics/messages, consumer lag and the Debezium connector |
| **connect** | `debezium/connect:2.7.3.Final` | `8083` | kafka, postgres | Kafka Connect running the Debezium Postgres connector |
| **connect-init** | `curlimages/curl:8.8.0` | — | connect | One-shot: `PUT`s the connector config from `docker/debezium/`, then exits |
| **indexer-worker** | built from `docker/Dockerfile` | — | kafka, elasticsearch | `sync_worker.py --role indexer` → Elasticsearch; waits for ES at startup, heartbeat healthcheck |
| **embedding-worker** | built from `docker/Dockerfile` | — | kafka, postgres | `sync_worker.py --role embedder` → pgvector (re-embeds only on text change); waits for Postgres at startup, heartbeat healthcheck |
| **redis** | `redis:7-alpine` | `6379` | — | Cache service |
| **prometheus** | `prom/prometheus:v2.53.1` | `9090` | app | Scrapes `/metrics` from the app + exporters; time-series store ([Monitoring](monitoring.md)) |
| **grafana** | `grafana/grafana:11.1.0` | `3000` | prometheus | Dashboards over Prometheus; datasource + **RAG - Overview** board auto-provisioned |
| **postgres-exporter** | `quay.io/prometheuscommunity/postgres-exporter:v0.15.0` | `9187` | postgres | Postgres metrics for Prometheus |
| **redis-exporter** | `oliver006/redis_exporter:v1.62.0` | `9121` | redis | Redis metrics for Prometheus |
| **elasticsearch-exporter** | `quay.io/prometheuscommunity/elasticsearch-exporter:v1.7.0` | `9114` | elasticsearch | Elasticsearch metrics for Prometheus |
| **kafka-exporter** | `danielqsj/kafka-exporter:v1.7.0` | `9308` | kafka | Kafka consumer-group **lag** + offsets (CDC freshness) |

### Startup order & health gating

Compose does not start a service until its dependencies report **healthy**:

- `postgres`, `elasticsearch` and `kafka` expose health checks; everything that talks to them waits (`depends_on: condition: service_healthy`).
- `connect-init` waits for `connect` to be healthy, `PUT`s
  `docker/debezium/product-catalog-connector.json` to
  `http://connect:8083/connectors/product-catalog-connector/config`
  (idempotent — safe on every `up`), prints a confirmation, and exits with `restart: "no"`.
- `indexer-worker` and `embedding-worker` run with `restart: unless-stopped`; on their first start they consume the Debezium **initial snapshot** (`auto.offset.reset=earliest`), which is how a fresh index gets bootstrapped.
- **Worker startup is resilient.** Beyond `depends_on`, each worker also *waits* for its own datastore before consuming: `ESKeywordSearch.setup()` and `VectorStore.setup()` retry with exponential backoff (up to ~30 attempts, 1→5 s) instead of crashing if Elasticsearch/Postgres is briefly unreachable. Each worker also writes a heartbeat file (`WORKER_HEARTBEAT_FILE`, default `/tmp/worker.heartbeat`) every poll, and a Compose `healthcheck` marks it unhealthy when that file goes stale (>30 s). So `docker compose ps` flags a genuinely hung/crashed worker, while one that is merely idling — waiting for the topic to appear — stays **healthy**.
- `app` depends only on `postgres`, `elasticsearch` and `redis` — not on Kafka/Connect — so the API can serve reads while the CDC pipeline is still warming up.

### 3. Load data (first time)

The stack does **not** auto-ingest. Seed the catalog and indexes once the
services are up:

```bash
# Writes all three targets: product_catalog + pgvector + Elasticsearch
docker compose exec app uv run python scripts/ingest.py

# Alternative: write only the source-of-truth catalog and let the CDC
# workers build both indexes from the Debezium snapshot
docker compose exec app uv run python scripts/ingest.py --catalog-only
```

After this, ongoing writes via `POST/PUT/DELETE /api/products` propagate to both
indexes automatically through CDC — see
[Hybrid Retrieval](../architecture/hybrid-retrieval.md#cdc-architecture-how-the-indexes-stay-fresh)
and [sync_worker.py](../scripts/sync-worker.md).

### 4. Verify everything is wired

```bash
# API up?
curl http://localhost:8000/health

# A recommendation (needs data ingested + provider key)
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Điện thoại chụp ảnh đẹp dưới 15 triệu", "top_k": 3}'

# Debezium connector registered & running?
curl http://localhost:8083/connectors/product-catalog-connector/status

# Elasticsearch keyword index populated?
curl "http://localhost:9200/product_chunks/_count?pretty"
```

The API is at `http://localhost:8000` (interactive docs at
`http://localhost:8000/docs`); Kibana is at `http://localhost:5601`; Kafka UI is
at `http://localhost:8080`.

---

## Managing the Stack

### Start / stop subsets

```bash
docker compose up -d postgres elasticsearch kafka   # just the infra
docker compose up -d kibana                          # add Kibana later
docker compose up -d kafka-ui                         # add Kafka UI later
docker compose up -d prometheus grafana \
  postgres-exporter redis-exporter \
  elasticsearch-exporter kafka-exporter               # add the monitoring stack
docker compose stop indexer-worker embedding-worker  # pause the CDC workers
docker compose restart connect-init                  # re-register the connector
```

### Logs

```bash
docker compose logs -f app                # API
docker compose logs -f embedding-worker   # CDC → pgvector
docker compose logs -f indexer-worker     # CDC → Elasticsearch
docker compose logs -f connect            # Debezium
docker compose logs connect-init          # connector registration result
```

### Rebuild after code changes

```bash
docker compose up --build -d
```

Docker layer caching means only changed layers rebuild. Editing `pyproject.toml`
triggers a full dependency reinstall; code-only changes are fast.

### Stop & reset

```bash
docker compose down          # stop, keep data volumes
docker compose down -v       # also delete volumes (pgdata, esdata, kafkadata)
```

Removing volumes wipes the catalog, vectors, Elasticsearch index **and** the
Kafka log (including Debezium offsets), so the next `up` + `ingest` starts
completely clean.

### Clear the data & re-ingest (keep the stack running)

To wipe the product data and start over **without** tearing down the containers
(and without losing the Kafka log), empty all three data stores, then re-run
`ingest.py`. The three stores are the source catalog (`product_catalog`), the
derived pgvector table (`products`), and the Elasticsearch keyword index
(`product_chunks`):

```bash
# 1. Postgres — empty the source catalog AND the derived pgvector table
docker compose exec postgres psql -U postgres -d rag_products \
  -c "TRUNCATE product_catalog, products;"

# 2. Elasticsearch — drop the keyword index (a 404 here is fine if it's already gone)
curl -X DELETE "http://localhost:9200/product_chunks"

# 3. Re-ingest — writes all three targets directly (catalog + pgvector + ES)
docker compose exec app uv run python scripts/ingest.py
```

`ingest.py` recreates the index and both tables on demand (`CREATE … IF NOT
EXISTS`), so truncating/dropping first is safe. Because it writes pgvector and
Elasticsearch **directly**, you don't have to wait for the CDC workers to rebuild
— the re-inserted catalog rows still flow through Debezium, but the embedding
worker skips re-embedding via each chunk's `content_hash`.

!!! warning "TRUNCATE is not propagated by CDC — clear the indexes yourself"
    The sync workers only apply row-level `c`/`u`/`d`/`r` events; a Debezium
    **TRUNCATE** event is ignored. So truncating `product_catalog` on its own does
    **not** clear `products` / `product_chunks` — you must empty those two stores
    explicitly (steps 1–2). If you'd rather let CDC do the deletion, run
    `DELETE FROM product_catalog;` (not `TRUNCATE`): each row emits a `d` event
    that the workers propagate to both indexes automatically (slower for a large
    catalog, and requires the workers to be running).

For a *total* clean slate — including the Kafka log and Debezium offsets — use
`docker compose down -v` (above) instead, then `up` + `ingest`.

---

## Inspecting the Data

### Elasticsearch — Kibana

For a full walkthrough (Dev Tools queries, Discover data views, KQL filters,
field reference), see **[Viewing Data in Kibana](kibana.md)**. Quick version —
open `http://localhost:5601`:

- **Dev Tools** (Management → Dev Tools) for raw queries:

  ```
  GET product_chunks/_search
  { "query": { "match_all": {} }, "size": 5 }
  ```

- **Discover** for a grid view: create a **Data View** with the index pattern
  `product_chunks`, and at the time-field step choose *"I don't want to use the
  time filter"* (the index has no timestamp field).

Or hit the REST API directly:

```bash
curl "http://localhost:9200/_cat/indices?v"
curl "http://localhost:9200/product_chunks/_search?pretty&size=3"
```

### Postgres — psql

```bash
# Source-of-truth catalog
docker compose exec postgres psql -U postgres -d rag_products \
  -c "SELECT product_id, name, price FROM product_catalog LIMIT 5;"

# Derived semantic index (chunk rows + metadata)
docker compose exec postgres psql -U postgres -d rag_products \
  -c "SELECT id, metadata->>'chunk_type' AS type FROM products LIMIT 5;"
```

### Kafka — Kafka UI

For a point-and-click view of topics, live messages, consumer-group lag and the
Debezium connector, open **[Kafka UI](kafka-ui.md)** at `http://localhost:8080`
(no login). It's the "Kibana for Kafka" in this stack — see the dedicated page
for a walkthrough.

### Kafka — topics & consumer lag

The same information is available from the CLI:

```bash
# List topics (the CDC topic is ragshop.public.product_catalog)
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --list

# Consumer groups (one per sync worker: rag-sync-indexer, rag-sync-embedder)
docker compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group rag-sync-embedder
```

The `--describe` output's `LAG` column shows how far behind a worker is — that
lag is exactly the eventual-consistency window between a catalog write and the
search index catching up.

### Debezium — connector status

```bash
curl http://localhost:8083/connectors                                   # list
curl http://localhost:8083/connectors/product-catalog-connector/status  # state + tasks
```

### Metrics & dashboards — Prometheus & Grafana

For request rate, latency, error rate, LLM-quota failures and CDC lag **over
time**, open Grafana at `http://localhost:3000` (admin / admin) — the
**RAG - Overview** dashboard is provisioned out of the box. Prometheus is at
`http://localhost:9090` (**Status → Targets** shows what's being scraped). The
app exposes its own metrics at `http://localhost:8000/metrics`. See
**[Monitoring](monitoring.md)** for the full flow, the metric reference and the
dashboard queries.

---

## Environment Variables

Set these via `.env` (repo root), `--env-file`, or `-e` flags. In the full
Compose stack the infra variables are set for you.

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `GEMINI_API_KEY` | Yes* | Google Gemini key — default provider for **both** LLM and embeddings |
| `ANTHROPIC_API_KEY` | No | Only if `llm_provider: anthropic` in `configs/settings.yaml` |
| `OPENAI_API_KEY` | No | Only if you switch the LLM/embedding provider to OpenAI |
| `DATABASE_URL` | Auto | Postgres DSN; set by Compose to `postgresql://postgres:postgres@postgres:5432/rag_products` |
| `ELASTICSEARCH_URL` | Auto | Set by Compose to `http://elasticsearch:9200` |
| `KAFKA_BOOTSTRAP_SERVERS` | Auto | Set by Compose to `kafka:9092` (for the sync workers) |
| `WORKER_HEARTBEAT_FILE` | Auto | Set by Compose (`/tmp/worker.heartbeat`) for the sync workers — the file each worker touches every poll and the healthcheck watches. Unset = heartbeat disabled |
| `KEYWORD_BACKEND` | Auto | `elasticsearch` in Compose; falls back to in-memory BM25 if ES is unreachable |
| `ENVIRONMENT` | No | `development` (default) or `production` |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

*You only need the key for the provider selected in `configs/settings.yaml`
(Gemini by default). Multiple keys are supported for rotation
(`GEMINI_API_KEY=key_a,key_b`).

## Ports & Volumes Reference

| Host port | Service | Use |
| --------- | ------- | --- |
| `8000` | app | REST API + Swagger UI |
| `5601` | kibana | Elasticsearch UI |
| `8080` | kafka-ui | Kafka UI (topics, messages, consumer lag, connector) |
| `9200` | elasticsearch | ES REST API |
| `5432` | postgres | SQL access (psql / DBeaver) |
| `8083` | connect | Kafka Connect / Debezium REST |
| `6379` | redis | Cache |
| `3000` | grafana | Dashboards (admin / admin) |
| `9090` | prometheus | Query UI + scrape-target status |
| `9187` | postgres-exporter | Postgres metrics |
| `9121` | redis-exporter | Redis metrics |
| `9114` | elasticsearch-exporter | Elasticsearch metrics |
| `9308` | kafka-exporter | Kafka lag/offset metrics |

The `app` also serves its own Prometheus metrics at `http://localhost:8000/metrics`.

| Volume | Service | Contents |
| ------ | ------- | -------- |
| `pgdata` | postgres | `product_catalog` + `products`/pgvector |
| `esdata` | elasticsearch | `product_chunks` keyword index |
| `kafkadata` | kafka | Event log + Debezium offsets |
| `promdata` | prometheus | Scraped metrics time-series history |
| `grafanadata` | grafana | Grafana state (dashboard edits, prefs) |

---

## Option 2 — Pre-Built GHCR Image (Minimal)

Best for a quick deployment or testing without cloning the repo. Every push to
`main` and every version tag builds and pushes an image to GitHub Container
Registry.

!!! warning "This is a minimal deployment"
    The example below runs only **app + Postgres + Redis** — no Elasticsearch,
    Kafka or Debezium. In that mode the keyword branch uses the in-memory BM25
    snapshot (built at startup) and there is **no CDC**, so catalog writes are
    reflected only after a re-ingest. For the full hybrid + real-time-sync
    behaviour, use Option 1.

### Available tags

| Tag | Description | Example |
| --- | ----------- | ------- |
| `main` | Latest commit on `main` | `ghcr.io/nxhawk/rag-product-recommend:main` |
| `v*.*.*` | Semantic version release | `ghcr.io/nxhawk/rag-product-recommend:v1.0.0` |
| `v*.*` | Major.minor (rolling) | `ghcr.io/nxhawk/rag-product-recommend:v1.0` |
| `<sha>` | Specific commit SHA | `ghcr.io/nxhawk/rag-product-recommend:a1b2c3d` |

### Pull & run

```bash
docker pull ghcr.io/nxhawk/rag-product-recommend:main

docker run -d \
  --name rag-api \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/nxhawk/rag-product-recommend:main
```

### Minimal Compose (app + Postgres + Redis)

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
      KEYWORD_BACKEND: memory   # no Elasticsearch in this minimal stack
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

## Troubleshooting

| Symptom | Likely cause & fix |
| ------- | ------------------ |
| `app` returns `503` on `/api/recommend` | No data ingested yet, or the provider API key is missing/invalid. Run `ingest.py` and check `.env`. |
| Recommendations work but keyword hits look weak | Elasticsearch unreachable → the API silently fell back to in-memory BM25. Check `docker compose logs elasticsearch` and `curl localhost:9200/_cluster/health`. |
| `connect-init` exits without registering | `connect` wasn't healthy yet. Re-run `docker compose up -d --force-recreate connect-init` and check `docker compose logs connect-init`. |
| `.../connectors/product-catalog-connector/status` returns `404 No status found` | The Debezium connector isn't registered, so the topic `ragshop.public.product_catalog` is never created and **both** indexes stay empty. Register it: `docker compose up -d --force-recreate connect-init` (or `PUT` the config manually), then re-check the status. |
| Catalog writes don't appear in search | A sync worker is down or lagging. Check `docker compose logs embedding-worker indexer-worker` and the consumer-group `LAG` (see above). |
| Elasticsearch has data but pgvector (`products`) is empty | Only the **embedding** worker failed — most often a missing/invalid `GEMINI_API_KEY` (the indexer needs no key). Check `docker compose logs embedding-worker`; add the key to `.env`, then `docker compose up -d --force-recreate embedding-worker`. |
| A worker keeps restarting right after startup | It can't reach its datastore. The workers now retry with backoff, so this self-heals once Postgres/Elasticsearch is up; if it persists, the dependency is genuinely down or on another network — check `docker compose ps` and that service's logs. |
| Elasticsearch container keeps restarting | Not enough memory. It's pinned to `-Xms512m -Xmx512m`; give Docker more RAM or lower `ES_JAVA_OPTS`. |
| Kafka UI shows no cluster / "offline" | The broker wasn't ready when it started, or `KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS` is wrong. Check `docker compose logs kafka-ui` and that `kafka` is healthy. |
| Port already in use | Another process holds `8000/5432/9200/5601/8080/8083/6379`. Stop it or remap the `ports:` entry. |

---

## CI/CD Pipeline

The GHCR image is built automatically by GitHub Actions
(`.github/workflows/docker.yml`):

1. **Test** — installs deps, runs `pytest tests/ -v`.
2. **Build & Push** — only if tests pass; pushes on `main` and tags (PRs build but don't push).

To trigger a versioned release, create a git tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

This produces images tagged `v1.0.0`, `v1.0`, and the commit SHA.
