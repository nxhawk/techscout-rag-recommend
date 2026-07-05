# Installation

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- A Gemini API key (the default provider for both the LLM and embeddings). Anthropic and/or OpenAI keys are optional — only needed if you switch providers in `configs/settings.yaml`.
- Docker + Docker Compose (recommended) — the full backing stack (Postgres/pgvector, Elasticsearch, Kafka, Debezium Connect, Redis) ships via `docker/docker-compose.yml`, so you do not need to install those services manually.

## Install uv

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

## Clone and Install

```bash
git clone https://github.com/nxhawk/rag-product-recommend.git
cd rag-product-recommend
uv sync
```

This installs all dependencies from `pyproject.toml` and creates a virtual environment automatically (like `npm install`).

## Environment Variables

Create a `.env` file in the project root and add your API key(s). The repo does not ship a `.env.example`, so create the file yourself:

```bash
# create a .env file (the repo does not ship a .env.example)
touch .env
```

By default the project uses Gemini for both the LLM and embeddings, so `GEMINI_API_KEY` is the only key you need. The other keys are optional and only required if you switch providers. The infra overrides all have sensible defaults (and are set automatically by Docker Compose).

| Variable                  | Required | Description                                                                             |
| ------------------------- | -------- | --------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`          | Yes*     | Google Gemini key — used by the default LLM and embedding providers                     |
| `ANTHROPIC_API_KEY`       | No       | Anthropic Claude key — only if you set `llm_provider: anthropic`                         |
| `OPENAI_API_KEY`          | No       | OpenAI key — only if you switch the LLM or embedding provider to OpenAI                  |
| `DATABASE_URL`            | No       | Postgres connection string (default `postgresql://postgres:postgres@localhost:5432/rag_products`) |
| `ELASTICSEARCH_URL`       | No       | Elasticsearch URL for the keyword index (default `http://localhost:9200`)               |
| `KAFKA_BOOTSTRAP_SERVERS` | No       | Kafka bootstrap address for CDC (default `localhost:9092`)                              |
| `KEYWORD_BACKEND`         | No       | `elasticsearch` (default) or `memory` for the in-memory BM25 fallback                   |

*At minimum you need the key for the configured provider. With the default config that is `GEMINI_API_KEY`.

## Install Dev Dependencies

```bash
uv sync --group dev
```

## Install Docs Dependencies

```bash
uv sync --group docs
```
