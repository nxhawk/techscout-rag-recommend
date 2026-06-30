# RAG Product Recommendation & Comparison

A product recommendation and comparison system powered by **RAG (Retrieval-Augmented Generation)**. Users ask natural language queries, the system retrieves relevant product data from a vector database, then an LLM generates contextual answers.

## Key Features

- **Product Recommendation** — Analyzes user intent (budget, purpose, priorities) → retrieves matching products → scores and ranks → LLM explains why each product fits.
- **Product Comparison** — Aligns specifications across products → compares each criterion → LLM produces detailed analysis with pros/cons and conclusions.
- **Smart Search** — Hybrid search (semantic + keyword + metadata filter) with cross-encoder reranking.
- **Vietnamese NLP** — Full support for Vietnamese queries and responses.

## Tech Stack

| Component    | Choice                                      |
| ------------ | ------------------------------------------- |
| Language     | Python 3.11+                                |
| Package Mgr  | [uv](https://docs.astral.sh/uv/)          |
| API          | FastAPI                                     |
| LLM          | Claude API / OpenAI GPT                     |
| Embedding    | text-embedding-3-small                      |
| Vector DB    | ChromaDB (dev) → Qdrant (prod)              |
| Cache        | Redis                                       |
| Container    | Docker + Docker Compose                     |
| Testing      | pytest                                      |
| Docs         | MkDocs Material                             |

## Quick Start

```bash
# 1. Install uv (if not installed)
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and install dependencies
git clone <repo-url>
cd rag-product-recommend
uv sync

# 3. Configure API keys
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY, OPENAI_API_KEY

# 4. Ingest sample data
uv run python scripts/ingest.py

# 5. Start API server
uv run uvicorn api.app:app --reload

# 6. Run tests
uv run pytest tests/
```

## API Endpoints

| Method | Endpoint         | Description          |
| ------ | ---------------- | -------------------- |
| POST   | `/api/recommend` | Product recommendation |
| POST   | `/api/compare`   | Product comparison     |
| POST   | `/api/search`    | Product search         |
| GET    | `/health`        | Health check           |

**Example request:**

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Phone with great camera under 15 million VND", "top_k": 3}'
```

## Project Structure

```
rag-product-recommend/
├── pyproject.toml              # Dependencies & project metadata
├── uv.lock                     # Lockfile (like package-lock.json)
├── .env                        # API keys (not committed)
│
├── src/                        # Core business logic
│   ├── ingestion/              # Data loading & normalization
│   │   ├── product_loader.py   #   Load from JSON/CSV
│   │   ├── review_loader.py    #   Load user reviews
│   │   ├── data_cleaner.py     #   Clean & normalize data
│   │   ├── spec_parser.py      #   Parse product specifications
│   │   ├── chunker.py          #   Field-based chunking
│   │   └── price_tracker.py    #   Price history tracking
│   │
│   ├── embedding/              # Embedding & Vector DB
│   │   ├── product_embedder.py #   Text → vector (OpenAI)
│   │   ├── multi_field_embedder.py  # Per-field embedding
│   │   └── vector_store.py     #   ChromaDB/Qdrant CRUD
│   │
│   ├── retrieval/              # Product retrieval
│   │   ├── product_retriever.py #  Combined filter + search
│   │   ├── hybrid_search.py    #   Semantic + keyword search
│   │   ├── filter_engine.py    #   Extract filters from NL query
│   │   ├── similarity_scorer.py #  Composite scoring
│   │   └── reranker.py         #   Cross-encoder reranking
│   │
│   ├── generation/             # LLM generation
│   │   ├── llm_client.py       #   Multi-provider LLM client
│   │   ├── response_parser.py  #   Parse JSON from LLM output
│   │   ├── guardrails.py       #   Input/output validation
│   │   └── prompt_templates/   #   Prompts per use case
│   │       ├── recommend_prompt.py
│   │       ├── compare_prompt.py
│   │       └── review_summary_prompt.py
│   │
│   ├── pipeline/               # Orchestration
│   │   ├── rag_router.py       #   Classify query → pipeline
│   │   ├── config.py           #   Pipeline configuration
│   │   ├── recommend_pipeline.py #  E2E recommendation flow
│   │   ├── compare_pipeline.py #   E2E comparison flow
│   │   ├── recommend/          #   Recommendation logic
│   │   │   ├── engine.py       #     Recommendation engine
│   │   │   ├── user_intent_parser.py  # Parse user intent
│   │   │   ├── scoring.py      #     Multi-criteria scoring
│   │   │   └── personalization.py #   User history boost
│   │   └── compare/            #   Comparison logic
│   │       ├── comparator.py   #     Compare N products
│   │       ├── spec_aligner.py #     Align specifications
│   │       ├── formatter.py    #     Format output
│   │       └── pros_cons_extractor.py
│   │
│   └── utils/                  # Utilities
│       ├── logger.py
│       ├── cache.py
│       └── helpers.py
│
├── api/                        # API layer (FastAPI)
│   ├── app.py                  #   FastAPI entry point
│   ├── schemas.py              #   Request/Response models
│   ├── deps.py                 #   Dependency injection
│   ├── routes/
│   │   ├── recommend.py
│   │   ├── compare.py
│   │   └── search.py
│   └── middleware/
│       ├── rate_limit.py       #   Rate limiting
│       └── error_handler.py    #   Error handling
│
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests
│
├── evaluation/                 # RAG quality evaluation
│   ├── eval_recommend.py
│   ├── eval_compare.py
│   └── test_cases.json
│
├── scripts/                    # CLI scripts
│   ├── ingest.py               #   Ingest data into vector store
│   └── seed.py                 #   Seed sample data
│
├── configs/
│   ├── settings.yaml           # Main config
│   ├── product_categories.yaml # Categories + required fields
│   └── scoring_weights.yaml    # Scoring weights per use case
│
├── docs/                       # MkDocs Material documentation
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
└── data/
    ├── raw/products/           # Raw data
    ├── processed/              # Normalized data
    └── embeddings/             # ChromaDB persist (gitignored)
```

## RAG Pipeline Flow

```
User Query
    │
    ▼
┌─────────────┐
│  RAG Router  │ ── Classify: RECOMMEND / COMPARE / INFO
└─────┬───────┘
      │
      ├── RECOMMEND ──────────────────────────┐
      │   Intent Parser → Filter → Retrieve   │
      │   → Rerank → Score → LLM → Response   │
      │                                        │
      └── COMPARE ────────────────────────────┐│
          Extract Products → Retrieve Specs   ││
          → Align → Compare → LLM → Response  ││
                                               ▼▼
                                          JSON Response
```

## Development

```bash
# Add a dependency
uv add <package>

# Add a dev dependency
uv add --group dev <package>

# Run any command inside the venv
uv run <command>

# Serve docs locally
uv run mkdocs serve

# Docker
cd docker
docker compose up --build
```

## Documentation

Full documentation is available at the [project docs site](https://nxhawk.github.io/rag-product-recommend/) (deployed via GitHub Pages).

To serve locally:

```bash
uv sync --group docs
uv run mkdocs serve
```

## Roadmap

See [PLAN.md](./PLAN.md) for the detailed phase-by-phase roadmap.

## License

MIT
