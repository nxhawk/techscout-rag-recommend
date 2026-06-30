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

Copy the example file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
# At least one LLM key is required
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

!!! tip "Which keys do I need?"
    You only need the key for the provider configured in `configs/settings.yaml`. By default the project uses **Anthropic** for LLM and **OpenAI** for embeddings, so at minimum you need `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`.

## Configuration

All pipeline settings live in `configs/settings.yaml`:

```yaml
# LLM provider: "anthropic" | "openai" | "gemini"
llm_provider: "anthropic"
llm_model: "claude-sonnet-4-6"

# Embedding (currently OpenAI only)
embedding_provider: "openai"
embedding_model: "text-embedding-3-small"

# Vector DB
vector_db: "chroma"
vector_db_path: "./data/embeddings"

# Retrieval
top_k_retrieve: 20
top_k_recommend: 5
top_k_compare: 3
```

The config is loaded as a `PipelineConfig` dataclass via `PipelineConfig.from_yaml()` and injected into components through `api/deps.py` factory functions.

## Data Ingestion

Before running the server, ingest product data into the vector store:

```bash
# Seed sample data (creates JSON files in data/raw/products/)
uv run python scripts/seed.py

# Ingest into ChromaDB
uv run python scripts/ingest.py
```

This will:

1. Load product data from `data/raw/products/`
2. Clean and normalize the data
3. Chunk product fields
4. Generate embeddings via OpenAI
5. Store vectors in ChromaDB at `data/embeddings/`

## Running the API Server

```bash
uv run uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

The server starts at `http://localhost:8000`. Key endpoints:

| Method | Endpoint         | Description            |
| ------ | ---------------- | ---------------------- |
| POST   | `/api/recommend` | Product recommendation |
| POST   | `/api/compare`   | Product comparison     |
| POST   | `/api/search`    | Product search         |
| GET    | `/health`        | Health check           |

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

The project includes a Docker Compose setup with the API server and Redis:

```bash
cd docker
docker compose up --build
```

This starts:

- **app** — the FastAPI server on port `8000`
- **redis** — Redis cache on port `6379`

The `data/` directory is mounted as a volume so the vector store persists across container restarts.

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
