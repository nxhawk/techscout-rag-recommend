# Docker Deployment

This guide covers two ways to run the project with Docker: building locally with Docker Compose, or pulling the pre-built image from GitHub Container Registry (GHCR).

## Option 1 — Docker Compose (Local Build)

Best for local development. Builds the image from source and starts the API server with Postgres (pgvector) and Redis.

### Prerequisites

- Docker Engine 20.10+
- Docker Compose v2

### Run

```bash
# 1. Configure environment variables
cp .env.example .env
# Edit .env with your API keys

# 2. Start all services
cd docker
docker compose up --build
```

This starts the full CDC stack:

| Service | Port | Description |
| ------- | ---- | ----------- |
| **app** | `8000` | FastAPI server (keyword backend: Elasticsearch) |
| **postgres** | `5432` | Postgres + pgvector — catalog (source of truth) + vectors; `wal_level=logical` for CDC |
| **elasticsearch** | `9200` | Keyword/BM25 index (`product_chunks`) |
| **kafka** | — | Event stream (single-node KRaft) |
| **connect** | `8083` | Debezium (Kafka Connect) — captures `product_catalog` changes |
| **connect-init** | — | One-shot: registers the Debezium connector (`docker/debezium/`), then exits |
| **indexer-worker** | — | CDC consumer → Elasticsearch |
| **embedding-worker** | — | CDC consumer → pgvector (re-embeds only on text changes) |
| **redis** | `6379` | Redis cache |

Product create/update/delete via `POST/PUT/DELETE /api/products` propagates
to both search indexes automatically (see
[Hybrid Retrieval](../architecture/hybrid-retrieval.md#cdc-architecture-how-the-indexes-stay-fresh)).

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Stop

```bash
docker compose down

# Remove volumes too (deletes cached data)
docker compose down -v
```

### Rebuild After Code Changes

```bash
docker compose up --build
```

Docker layer caching means only changed layers rebuild. Dependency changes (editing `pyproject.toml`) trigger a full reinstall; code-only changes are fast.

### Data Persistence

Vectors live in Postgres, persisted in the named volume `pgdata`. The `data/` directory is still mounted for raw product data:

```yaml
volumes:
  - ../data:/app/data   # raw data (app service)
  - pgdata:/var/lib/postgresql/data   # vectors (postgres service)
```

If you need a clean vector store, drop the volume and re-run ingestion:

```bash
docker compose down -v   # removes pgdata
docker compose up -d
docker compose exec app uv run python scripts/ingest.py
```

---

## Option 2 — Pre-Built GHCR Image

Best for deployment or quick testing without cloning the repo. Every push to `main` and every version tag automatically builds and pushes an image to GitHub Container Registry.

### Available Tags

| Tag | Description | Example |
| --- | ----------- | ------- |
| `main` | Latest commit on `main` branch | `ghcr.io/nxhawk/rag-product-recommend:main` |
| `v*.*.*` | Semantic version release | `ghcr.io/nxhawk/rag-product-recommend:v1.0.0` |
| `v*.*` | Major.minor (rolling) | `ghcr.io/nxhawk/rag-product-recommend:v1.0` |
| `<sha>` | Specific commit SHA | `ghcr.io/nxhawk/rag-product-recommend:a1b2c3d` |

### Pull & Run

```bash
# Pull the latest image
docker pull ghcr.io/nxhawk/rag-product-recommend:main

# Run with environment variables
docker run -d \
  --name rag-api \
  -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e OPENAI_API_KEY=sk-... \
  -e ENVIRONMENT=production \
  -v $(pwd)/data:/app/data \
  ghcr.io/nxhawk/rag-product-recommend:main
```

### Run with `.env` File

```bash
docker run -d \
  --name rag-api \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  ghcr.io/nxhawk/rag-product-recommend:main
```

### Run with Redis (Docker Compose)

Create a `docker-compose.prod.yml`:

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

## Environment Variables

These variables must be set either via `--env-file`, `-e` flags, or in the `.env` file:

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic Claude API key |
| `OPENAI_API_KEY` | Yes* | OpenAI API key (used for embeddings) |
| `GEMINI_API_KEY` | No | Google Gemini API key |
| `DATABASE_URL` | No | Postgres connection string (default: `postgresql://postgres:postgres@localhost:5432/rag_products`; set automatically by Docker Compose) |
| `ENVIRONMENT` | No | `development` (default) or `production` |
| `LOG_LEVEL` | No | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

*At minimum you need the key for the configured LLM provider (`ANTHROPIC_API_KEY` by default) and `OPENAI_API_KEY` for embeddings.

---

## Data Ingestion in Docker

The container does not auto-ingest data. You need to run ingestion manually:

```bash
# If running with docker compose
docker compose exec app uv run python scripts/seed.py
docker compose exec app uv run python scripts/ingest.py
# or: ingest.py --catalog-only  (let the CDC workers build the indexes)

# If running standalone container
docker exec rag-api uv run python scripts/seed.py
docker exec rag-api uv run python scripts/ingest.py
```

After ingestion, vectors are stored in Postgres (the `pgdata` volume) and persist across restarts.

---

## Health Check

Verify the server is running:

```bash
curl http://localhost:8000/health
```

Test a recommendation request:

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Điện thoại chụp ảnh đẹp dưới 15 triệu", "top_k": 3}'
```

---

## Useful Commands

```bash
# View logs
docker compose logs -f app

# Shell into the container
docker compose exec app bash

# Check image size
docker images ghcr.io/nxhawk/rag-product-recommend

# Remove old images
docker image prune -f
```

---

## CI/CD Pipeline

The GHCR image is built automatically by GitHub Actions (`.github/workflows/docker.yml`):

1. **Test** — installs deps, runs `pytest tests/ -v`
2. **Build & Push** — only if tests pass; only pushes on `main` branch and tags (PRs build but don't push)

To trigger a versioned release, create a git tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

This produces images tagged `v1.0.0`, `v1.0`, and the commit SHA.
