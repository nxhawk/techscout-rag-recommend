# Development Guide

This guide walks you through setting up the project for local development, running the server, executing tests, and working with Docker.

## Prerequisites

- **Python 3.11+** — required by the project
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (replaces pip)
- **Git**
- **Docker + Docker Compose** (optional, for containerized setup)

### Install uv

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

## Clone & Install

```bash
git clone https://github.com/nxhawk/rag-product-recommend.git
cd rag-product-recommend

# Install all dependencies (including dev + docs groups)
uv sync --group dev --group docs
```

`uv sync` reads `pyproject.toml`, resolves versions from `uv.lock`, and creates a virtual environment automatically. No need to manually create a venv.

## Environment Variables

Create a `.env` file in the project root and add your API key(s). The repo does not ship a `.env.example`:

```dotenv
# Default provider is Gemini (LLM + embeddings) — this is the only key you need
GEMINI_API_KEY=AIza...

# Optional — only if you switch providers in configs/settings.yaml
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Optional infra overrides (all have sensible defaults)
ELASTICSEARCH_URL=http://localhost:9200
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KEYWORD_BACKEND=elasticsearch

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

!!! tip "Which keys do I need?"
    You only need the key for the provider configured in `configs/settings.yaml`. By default the project uses **Gemini** for both the LLM and embeddings, so at minimum you need `GEMINI_API_KEY`. `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` are only needed if you switch providers. `ELASTICSEARCH_URL`, `KAFKA_BOOTSTRAP_SERVERS`, and `KEYWORD_BACKEND` are optional overrides for the CDC/keyword stack.

## Configuration

All pipeline settings live in `configs/settings.yaml`:

```yaml
# LLM provider: "gemini" | "anthropic" | "openai"
llm_provider: "gemini"
llm_model: "gemini-2.5-flash"

# Embedding provider: "gemini" | "openai"
embedding_provider: "gemini"
embedding_model: "gemini-embedding-001"

# Vector DB (Postgres + pgvector)
vector_db: "pgvector"
vector_db_url: "postgresql://postgres:postgres@localhost:5432/rag_products"  # overridden by DATABASE_URL
embedding_dim: 768

# Retrieval
top_k_retrieve: 20
top_k_recommend: 5
top_k_compare: 3

# Hybrid retrieval (BM25 + Reciprocal Rank Fusion)
use_bm25: true
rrf_k: 60
keyword_candidates: 50

# Keyword backend: "elasticsearch" (CDC-synced, pre-filtered) or "memory"
# (in-memory BM25 fallback). Falls back to memory automatically if ES is down.
keyword_backend: "elasticsearch"
es_url: "http://localhost:9200"          # overridden by ELASTICSEARCH_URL
es_index: "product_chunks"

# CDC sync (Debezium -> Kafka -> sync workers)
kafka_bootstrap: "localhost:9092"                 # overridden by KAFKA_BOOTSTRAP_SERVERS
products_topic: "ragshop.public.product_catalog"
catalog_table: "product_catalog"                  # source-of-truth table
```

The config is loaded as a `PipelineConfig` dataclass via `PipelineConfig.from_yaml()` and injected into components through `api/deps.py` factory functions.

## Data Ingestion

Before running the server, start Postgres and ingest product data:

```bash
# Start Postgres with pgvector (Docker)
cd docker && docker compose up -d postgres && cd ..

# Seed sample data (creates JSON files in data/raw/products/)
uv run python scripts/seed.py

# Ingest — default mode writes catalog + pgvector + Elasticsearch
uv run python scripts/ingest.py

# Or catalog-only: write ONLY product_catalog and let the CDC sync workers
# build both indexes from the Debezium initial snapshot
uv run python scripts/ingest.py --catalog-only
```

The default mode will:

1. Load product data from `data/raw/products/`
2. Clean and normalize the data
3. Chunk product fields
4. Generate embeddings via Gemini
5. Write the `product_catalog` table (the source of truth)
6. Store vectors in the `products` table in Postgres (pgvector, HNSW cosine index)
7. Bulk-upsert the keyword index into Elasticsearch (skipped if ES is unreachable)

The `--catalog-only` flag writes only `product_catalog`; the running sync workers then build both derived indexes from the CDC snapshot. Note the source-of-truth table is `product_catalog`, while the vector store table is `products`.

### Running the CDC Sync Workers (without Docker)

The two sync workers keep the derived indexes fresh from the Debezium change stream. In Docker they run automatically as the **indexer-worker** and **embedding-worker** services; to run them locally without Docker:

```bash
# Indexer worker → Elasticsearch keyword index
uv run python scripts/sync_worker.py --role indexer

# Embedding worker → pgvector (re-embeds only on text changes)
uv run python scripts/sync_worker.py --role embedder
```

Both require Kafka, Elasticsearch, and Postgres to be reachable, and the Debezium connector to be registered (the `connect-init` service does this in Docker).

## Running the API Server

```bash
uv run uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

The server starts at `http://localhost:8000`. Key endpoints:

| Method            | Endpoint         | Description                    |
| ----------------- | ---------------- | ------------------------------ |
| POST              | `/api/recommend` | Product recommendation         |
| POST              | `/api/compare`   | Product comparison             |
| POST              | `/api/search`    | Product search                 |
| GET/POST/PUT/DELETE | `/api/products` | Catalog CRUD (source of truth) |
| GET               | `/health`        | Health check                   |

Interactive API docs are available at `http://localhost:8000/docs` (Swagger UI).

### Example Request

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Điện thoại chụp ảnh đẹp dưới 15 triệu", "top_k": 3}'
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run only unit tests
uv run pytest tests/unit/ -v

# Run only integration tests
uv run pytest tests/integration/ -v

# Run with coverage
uv run pytest tests/ --cov=src --cov=api
```

!!! note
    To use `--cov`, add `pytest-cov` first: `uv add --group dev pytest-cov`

## Docker

The project includes a Docker Compose setup that runs the full CDC stack:

```bash
cd docker
docker compose up --build
```

This starts:

- **app** — the FastAPI server on port `8000`
- **postgres** — Postgres + pgvector (catalog source of truth + vectors), `wal_level=logical` for CDC
- **redis** — Redis cache on port `6379`
- **elasticsearch** — BM25 keyword index (`product_chunks`) on port `9200`
- **kafka** — single-node KRaft event stream on port `9092`
- **connect** — Debezium (Kafka Connect) on port `8083`
- **connect-init** — one-shot job that registers the Debezium connector, then exits
- **indexer-worker** — CDC consumer → Elasticsearch
- **embedding-worker** — CDC consumer → pgvector

See the [Docker deployment guide](../deployment/docker.md) for volumes, lifecycle commands, and the pre-built GHCR image. The `data/` directory is mounted as a volume and vectors persist in the `pgdata` named volume across container restarts.

### Build Image Only

```bash
docker build -f docker/Dockerfile -t rag-product-recommend .
```

## Serving Docs Locally

```bash
uv run mkdocs serve
```

Opens at `http://localhost:8000` (or `8001` if `8000` is taken). Changes to `docs/` files hot-reload automatically.

## Common Commands Reference

| Command | Description |
| ------- | ----------- |
| `uv sync` | Install/update all dependencies |
| `uv add <pkg>` | Add a production dependency |
| `uv add --group dev <pkg>` | Add a dev dependency |
| `uv run <cmd>` | Run a command inside the venv |
| `uv run pytest tests/ -v` | Run tests |
| `uv run uvicorn api.app:app --reload` | Start dev server |
| `uv run mkdocs serve` | Serve docs locally |
| `uv run mkdocs build --strict` | Build docs (CI mode) |

## Dependency Management

This project uses **uv** with `pyproject.toml` (similar to `package.json` in Node.js). The lockfile `uv.lock` pins exact versions (like `package-lock.json`).

- **Production deps** — listed under `[project] dependencies`
- **Dev deps** — under `[dependency-groups] dev` (pytest, etc.)
- **Docs deps** — under `[dependency-groups] docs` (mkdocs-material, etc.)

Never install packages with `pip install` directly. Always use `uv add`.
