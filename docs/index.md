# RAG Product Recommendation

A product recommendation and comparison system powered by **Retrieval-Augmented Generation (RAG)**.

Users ask natural language queries, the system retrieves relevant product data from a vector database, then an LLM generates contextual, well-reasoned answers

## Key Features

- **Product Recommendation** — Analyzes user intent (budget, purpose, priorities), retrieves matching products, scores and ranks them, then generates explanations via LLM.
- **Product Comparison** — Aligns specifications across products, compares each criterion, and produces a detailed analysis with pros/cons and conclusions.
- **Smart Search** — Hybrid search combining semantic similarity, keyword matching, and metadata filtering, with cross-encoder reranking.
- **Multi-provider LLM** — Supports both Anthropic Claude and OpenAI GPT as generation backends.

## Quick Links

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md)
- [Architecture Overview](architecture/overview.md)
- [API Reference](api/endpoints.md)
