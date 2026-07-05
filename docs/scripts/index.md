# Scripts Overview

The `scripts/` folder contains CLI entry points for operating the system outside the API:

| Script | Purpose | Typical command |
|---|---|---|
| [`crawl.py`](crawl.md) | Crawl raw product data from configured sources into `data/raw/crawled/` | `uv run python scripts/crawl.py --all` |
| [`ingest.py`](ingest.md) | Clean, chunk, embed and load products into the vector store | `uv run python scripts/ingest.py --source crawled` |
| [`seed.py`](seed.md) | Seed sample data for development (placeholder) | `uv run python scripts/seed.py` |

The usual end-to-end order is **crawl → ingest**: the crawler writes
`data/raw/crawled/<source>/latest.json`, and the ingest script reads exactly those
files by default (`--source crawled`).

```mermaid
flowchart LR
    A[scripts/crawl.py] -->|"data/raw/crawled/&lt;source&gt;/latest.json"| B[scripts/ingest.py]
    B -->|embeddings + metadata| C[(Postgres + pgvector)]
    C --> D[API pipelines<br/>recommend / compare]
```

Each page below documents the full execution flow of a script: which functions are
called, in which order, and which file each one lives in.
