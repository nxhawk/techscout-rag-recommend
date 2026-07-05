# RAG Product Recommendation & Comparison

A product recommendation and comparison system powered by **RAG
(Retrieval-Augmented Generation)**. Users ask natural language queries (in
Vietnamese), the system retrieves relevant product data with **hybrid search**
(semantic + keyword), then an LLM generates contextual answers. Product data
flows through a **Change-Data-Capture (CDC)** pipeline, so the search indexes
stay in sync with a single source of truth automatically.

## Key Features

- **Product Recommendation** — Analyzes user intent (budget, purpose, priorities) → retrieves matching products → scores and ranks → LLM explains why each product fits.
- **Product Comparison** — Aligns specifications across products → compares each criterion → LLM produces detailed analysis with pros/cons and conclusions.
- **Hybrid Search** — Semantic search (pgvector) fused with a keyword branch (**Elasticsearch** BM25 in production, in-memory fallback) via Reciprocal Rank Fusion, with metadata filters pushed down on both branches and optional cross-encoder reranking.
- **Real-time Catalog Sync (CDC)** — The `product_catalog` table is the single source of truth; **Debezium** streams row changes through **Kafka** to two sync workers that keep Elasticsearch and pgvector fresh (eventual consistency, usually seconds) — no dual writes.
- **Product CRUD API** — `POST/PUT/DELETE /api/products` write only to the catalog; the indexes update themselves via CDC.
- **Web Crawling** — Collects live specs and reviews from e-commerce sites (thegioididong.com, cellphones.com.vn) to seed the catalog.
- **Vietnamese NLP** — Full support for Vietnamese queries and responses.
- **Multi-provider LLM** — Google Gemini (default), Anthropic Claude, or OpenAI GPT, selectable via config.

## Tech Stack

| Component     | Choice                                                        |
| ------------- | ------------------------------------------------------------- |
| Language      | Python 3.11+                                                  |
| Package Mgr   | [uv](https://docs.astral.sh/uv/)                              |
| API           | FastAPI + uvicorn                                             |
| LLM           | Google Gemini (default) / Anthropic Claude / OpenAI GPT       |
| Embedding     | Gemini `gemini-embedding-001` (768-dim; provider-selectable)  |
| Vector DB     | PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) (HNSW, cosine) |
| Keyword search| Elasticsearch 8 (BM25, index `product_chunks`)               |
| CDC pipeline  | Debezium (Postgres connector) + Apache Kafka (KRaft)          |
| ES UI         | Kibana                                                        |
| Crawling      | httpx + BeautifulSoup + lxml (tenacity for retries)          |
| Cache         | Redis                                                        |
| Container     | Docker + Docker Compose                                       |
| Testing       | pytest                                                       |
| Docs          | MkDocs Material (bilingual EN/VI)                            |

## Architecture at a Glance

Two flows keep the system consistent and fast:

**Query path (online, per request):**

```
User Query
    │
    ▼
┌─────────────┐
│  RAG Router │ ── Classify: RECOMMEND / COMPARE / INFO / HYBRID
└─────┬───────┘
      │
      ├── RECOMMEND ── Intent Parser → Filter → Hybrid Retrieve
      │                → Rerank → Score → LLM → Response
      │
      └── COMPARE ──── Extract Products → Retrieve Specs
                       → Align → Compare → LLM → Response
                                                   │
                                                   ▼
                                             JSON Response
```

Hybrid retrieval fuses **pgvector** (semantic) and **Elasticsearch** (keyword
BM25) with Reciprocal Rank Fusion.

**Write path (continuous, CDC):**

```
POST/PUT/DELETE /api/products ─┐
scripts/ingest.py ─────────────┴──► product_catalog (source of truth, Postgres)
                                          │  WAL (logical decoding)
                                          ▼
                                      Debezium ──► Kafka topic
                                                      │
                                   ┌──────────────────┴──────────────────┐
                                   ▼                                      ▼
                          indexer worker                        embedding worker
                          → Elasticsearch                       → pgvector
                          (product_chunks)                      (re-embed only on text change)
```

See the [CDC Sync](https://nxhawk.github.io/rag-product-recommend/architecture/cdc/),
[Write Path](https://nxhawk.github.io/rag-product-recommend/architecture/write-path/),
[Data Flow](https://nxhawk.github.io/rag-product-recommend/architecture/data-flow/) and
[C4 Model](https://nxhawk.github.io/rag-product-recommend/architecture/c4-model/) docs pages
for the full picture.

## Quick Start

The full stack (API, Postgres/pgvector, Elasticsearch, Kafka, Debezium, the two
sync workers, Redis and Kibana) runs from Docker Compose:

```bash
# 1. Install uv (if not installed)
#   Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
#   macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and install dependencies
git clone <repo-url>
cd rag-product-recommend
uv sync

# 3. Configure API keys — create a .env at the project root.
#    Default provider is Gemini (LLM + embeddings):
#      GEMINI_API_KEY=...
#      # ANTHROPIC_API_KEY / OPENAI_API_KEY only if you switch providers
#      ENVIRONMENT=development
#      LOG_LEVEL=INFO

# 4. Start the full stack (API + datastores + CDC pipeline + Kibana)
cd docker && docker compose up --build -d && cd ..

# 5. Seed the catalog + search indexes
docker compose -f docker/docker-compose.yml exec app uv run python scripts/ingest.py
#   or: ingest.py --catalog-only  (let the CDC workers build the indexes)

# 6. Try it — API at http://localhost:8000, Kibana at http://localhost:5601
```

Prefer running the API outside Docker? Start Postgres (and optionally
Elasticsearch/Kafka) with Compose, then `uv run uvicorn api.app:app --reload`.
See the [docs](https://nxhawk.github.io/rag-product-recommend/getting-started/quickstart/)
for the minimal path.

## API Endpoints

| Method | Endpoint                     | Description                          |
| ------ | ---------------------------- | ------------------------------------ |
| POST   | `/api/recommend`             | Product recommendation               |
| POST   | `/api/compare`               | Product comparison                   |
| POST   | `/api/search`                | Product search                       |
| POST   | `/api/products`              | Create a product (source of truth)   |
| PUT    | `/api/products/{id}`         | Update a product (partial)           |
| DELETE | `/api/products/{id}`         | Delete a product                     |
| GET    | `/api/products`, `/api/products/{id}` | Read the catalog            |
| GET    | `/health`                    | Health check                         |

Writes via `/api/products` hit only `product_catalog`; the CDC workers propagate
the change to both search indexes.

**Example request:**

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Phone with great camera under 15 million VND", "top_k": 3}'
```

## Project Structure

```
rag-product-recommend/
├── pyproject.toml       # Dependencies & project metadata
├── uv.lock              # Lockfile
├── CLAUDE.md            # AI coding rules + exhaustive per-file structure reference
├── .env                 # API keys (not committed)
│
├── src/                 # Core business logic
│   ├── crawler/         #   Web crawling → data/raw/crawled/ (spiders/ per source)
│   ├── ingestion/       #   Load, clean, parse specs, chunk raw product data
│   ├── catalog/         #   product_catalog source of truth (CRUD, REPLICA IDENTITY FULL)
│   ├── embedding/       #   Text → vector + vector store CRUD (Postgres/pgvector)
│   ├── retrieval/       #   Hybrid search, Elasticsearch keyword backend, filters, scoring, reranking
│   ├── sync/            #   CDC sync workers (Debezium → Elasticsearch / pgvector)
│   ├── generation/      #   Multi-provider LLM client, prompt templates, guardrails
│   ├── pipeline/        #   Orchestration: RAG router + recommend/compare pipelines
│   └── utils/           #   Logger, cache, helpers
│
├── api/                 # FastAPI layer
│   ├── app.py           #   Entry point
│   ├── schemas.py       #   Request/response models (incl. Product CRUD)
│   ├── deps.py          #   Dependency injection factories
│   ├── routes/          #   recommend.py, compare.py, search.py, products.py
│   └── middleware/      #   rate_limit.py, error_handler.py
│
├── tests/               # pytest suite (unit/, integration/)
├── evaluation/          # RAG quality evaluation scripts + test cases
├── scripts/             # CLI: crawl.py, ingest.py, sync_worker.py, seed.py
│
├── configs/             # settings.yaml, crawler.yaml, product_categories.yaml, scoring_weights.yaml
├── docs/                # MkDocs Material documentation (EN + VI)
├── docker/              # Dockerfile, docker-compose.yml (full CDC stack), debezium/ connector config
│
└── data/
    ├── raw/products/    # Curated sample data (tracked)
    ├── raw/crawled/     # Raw crawler output (gitignored)
    └── processed/       # Cleaned/chunked data (gitignored)
```

## Development

```bash
# Add a dependency
uv add <package>

# Add a dev dependency
uv add --group dev <package>

# Run any command inside the venv
uv run <command>

# Crawl a specific source/category
uv run python scripts/crawl.py --source tgdd --category smartphone

# Run a CDC sync worker standalone (needs Kafka + ES/Postgres reachable)
uv run python scripts/sync_worker.py --role indexer     # -> Elasticsearch
uv run python scripts/sync_worker.py --role embedder    # -> pgvector

# Serve docs locally
uv sync --group docs
uv run mkdocs serve

# Docker (full stack)
cd docker
docker compose up --build
```

## Documentation

Full documentation (English + Vietnamese) is at the
[project docs site](https://nxhawk.github.io/rag-product-recommend/) (deployed via
GitHub Pages, see `.github/workflows/docs.yml`). Highlights:

- [CDC Sync](https://nxhawk.github.io/rag-product-recommend/architecture/cdc/) — how the indexes stay in sync
- [Hybrid Retrieval](https://nxhawk.github.io/rag-product-recommend/architecture/hybrid-retrieval/) — semantic + BM25 + RRF
- [Docker Deployment](https://nxhawk.github.io/rag-product-recommend/deployment/docker/) — the full Compose stack
- [Viewing Data in Kibana](https://nxhawk.github.io/rag-product-recommend/deployment/kibana/) — inspect Elasticsearch

To serve locally:

```bash
uv sync --group docs
uv run mkdocs serve
```

## Roadmap

See [PLAN.md](./PLAN.md) for the detailed phase-by-phase roadmap.

## License

MIT
