# Quick Start

## Recommended: Start the Full Stack with Docker

The fastest way to get everything running is Docker Compose. From the `docker/` folder:

```bash
cd docker
docker compose up --build
```

This starts the **whole stack**, not just the API:

- **app** — the FastAPI server on port `8000`
- **postgres** — Postgres + pgvector: the `product_catalog` (source of truth) plus the vector index, started with `wal_level=logical` for CDC
- **elasticsearch** — the BM25 keyword index (`product_chunks`) on port `9200`
- **kafka** — single-node KRaft event stream on port `9092`
- **connect** — Debezium (Kafka Connect) on port `8083`, capturing `product_catalog` changes
- **connect-init** — one-shot job that registers the Debezium connector idempotently, then exits
- **indexer-worker** — CDC consumer that keeps Elasticsearch fresh
- **embedding-worker** — CDC consumer that keeps pgvector fresh
- **redis** — cache on port `6379`

The API is available at `http://localhost:8000`, with interactive docs at `http://localhost:8000/docs`. See the [Docker deployment guide](../deployment/docker.md) for full details, volumes, and lifecycle commands.

After the stack is up, ingest sample data inside the running container:

```bash
docker compose exec app uv run python scripts/seed.py
docker compose exec app uv run python scripts/ingest.py
```

## Manual / Minimal Setup

If you only want the core (no Docker for the app), you can run the backing services and the API separately.

### 1. Start Postgres (pgvector)

At minimum you need Postgres with pgvector. Optionally also start Elasticsearch, Kafka, and Debezium Connect if you want the full CDC-backed keyword search:

```bash
cd docker

# Core only — Postgres
docker compose up -d postgres

# Or the full backing stack for CDC keyword search
docker compose up -d postgres elasticsearch kafka connect connect-init
```

By default the app connects to `postgresql://postgres:postgres@localhost:5432/rag_products`. Override with the `DATABASE_URL` environment variable or `vector_db_url` in `configs/settings.yaml`.

!!! note "Retrieval without Elasticsearch"
    If you run without Elasticsearch and Kafka, retrieval still works: the API automatically falls back to an in-memory BM25 index for the keyword branch of hybrid search.

### 2. Ingest Sample Data

There are two ingestion modes:

```bash
# Default: writes all three targets — product_catalog, pgvector, and Elasticsearch
uv run python scripts/ingest.py

# Catalog-only: writes only product_catalog and lets the CDC sync workers
# build both indexes from the Debezium initial snapshot
uv run python scripts/ingest.py --catalog-only
```

The default mode reads products from `data/raw/`, chunks them by field (description, specs, pros/cons, reviews), generates embeddings, writes vectors to pgvector, bulk-upserts the keyword index into Elasticsearch (skipped if ES is down), and writes the `product_catalog` source of truth. The `--catalog-only` mode writes only the catalog; the running sync workers then build Elasticsearch and pgvector automatically from the CDC snapshot.

### 3. Start the API Server

```bash
uv run uvicorn api.app:app --reload
```

The server runs at `http://localhost:8000`. Interactive docs available at `http://localhost:8000/docs`.

## Try a Recommendation

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Phone with great camera under 15 million VND", "top_k": 3}'
```

## Try a Comparison

```bash
curl -X POST http://localhost:8000/api/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "Compare iPhone 15 Pro Max vs Samsung Galaxy S24 Ultra"}'
```

## Try a Search

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "gaming laptop with RTX 4060", "top_k": 5}'
```

## Manage the Catalog (CRUD)

The `product_catalog` table is the source of truth. Create a product through the CRUD API and the change propagates to the search indexes automatically via CDC:

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

Within a few seconds the Debezium → Kafka → sync-worker pipeline updates both Elasticsearch and pgvector, so the new product becomes searchable without any manual re-ingest.

## Run Tests

```bash
uv run pytest tests/
```
