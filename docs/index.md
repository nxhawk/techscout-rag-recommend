# RAG Product Recommendation

A product recommendation and comparison system powered by **Retrieval-Augmented Generation (RAG)**.

Users ask natural language queries, the system retrieves relevant product data from a vector database, then an LLM generates contextual, well-reasoned answers

## Key Features

- **Product Recommendation** — Analyzes user intent (budget, purpose, priorities), retrieves matching products, scores and ranks them, then generates explanations via LLM.
- **Product Comparison** — Aligns specifications across products, compares each criterion, and produces a detailed analysis with pros/cons and conclusions.
- **Smart Search** — Hybrid search combining semantic similarity with a keyword branch backed by Elasticsearch (BM25) in production (in-memory fallback in dev), fused via Reciprocal Rank Fusion (RRF), plus metadata filtering and cross-encoder reranking.
- **Real-time Catalog Sync (CDC)** — The `product_catalog` table is the source of truth; Debezium streams row changes through Kafka to two sync workers that keep the Elasticsearch and pgvector indexes fresh automatically (eventual consistency, usually a few seconds).
- **Multi-provider LLM** — Supports Anthropic Claude, OpenAI GPT, and Google Gemini as generation backends (Gemini is the default).

## Quick Links

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md)
- [Architecture Overview](architecture/overview.md)
- [Data Flow](architecture/data-flow.md)
- [API Reference](api/endpoints.md)
