# Architecture Overview

The system follows a standard RAG architecture with five core layers:

## End-to-End Flow

The diagram below covers the full system: the **offline** ingestion path that populates the vector store, and the **online** path that serves a single user query.

```mermaid
flowchart TD
    subgraph Offline["Data Ingestion (offline, batch)"]
        direction TB
        SRC["E-commerce sites\n(TGDD, CellphoneS)"] --> CRAWL[Crawler]
        CRAWL --> RAW[("data/raw/crawled/")]
        RAW --> CLEAN[DataCleaner]
        CLEAN --> SPEC[SpecParser]
        SPEC --> CHUNK["Chunker\n(field-based chunks)"]
        CHUNK --> EMBED[ProductEmbedder]
        EMBED --> VDB[("Postgres + pgvector\nvectors + metadata")]
        CLEAN -->|"upsert profiles\n(bootstrap)"| CAT
    end

    subgraph Sync["Catalog & CDC Sync (continuous)"]
        direction TB
        CRUD["Product CRUD API\nPOST/PUT/DELETE /api/products"] --> CAT[("product_catalog\nsource of truth")]
        CAT -->|"WAL → Debezium"| KAFKA["Kafka topic"]
        KAFKA --> IW["Indexer worker"]
        IW --> ESI[("Elasticsearch\nBM25 keyword index")]
        KAFKA --> EW["Embedding worker\n(re-embed only on\ntext change)"]
        EW --> VDB
    end

    subgraph Online["Query Processing (online, per-request)"]
        direction TB
        Q[User Query] --> GIN["Input Guardrail\n(normalize + heuristics + injection)"]
        GIN -->|block| E422["HTTP 422\n(Vietnamese reason)"]
        GIN -->|allow / sanitize| ROUTER{RAG Router}

        ROUTER -->|RECOMMEND| RI[UserIntentParser]
        RI --> RF[FilterEngine]
        RF --> RR[ProductRetriever]
        RR --> RRK[CrossEncoderReranker]
        RRK --> RSC[ProductScorer]

        ROUTER -->|COMPARE| CX[Extract Products]
        CX --> CR[ProductRetriever]
        CR --> CAL[SpecAligner]
        CAL --> CFM[ComparisonFormatter]

        RSC --> GCTX["Context Guardrail\n(sanitize product text)"]
        CFM --> GCTX
        GCTX --> LLM["LLM Client\n(Anthropic / OpenAI / Gemini)"]
        LLM --> RP[ResponseParser]
        RP --> GOUT["Output Guardrail\n(schema validate + grounding)"]
        GOUT -->|invalid / ungrounded| FB["Deterministic Fallback\n(no second LLM call)"]
        GOUT -->|valid & grounded| RESP["JSON Response\n+ warnings[]"]
        FB --> RESP
    end

    VDB -.->|vector + metadata search| RR
    VDB -.->|vector + metadata search| CR
    ESI -.->|"BM25 keyword search\n(pre-filtered)"| RR
```

## End-to-End Sequence

The sequence diagram below shows the same online path as a single request timeline, including the `RECOMMEND` vs `COMPARE` branch.

```mermaid
sequenceDiagram
    actor User
    participant API as FastAPI Route
    participant Pipe as Recommend/Compare Pipeline
    participant Guard as Guardrails (src/guardrails/)
    participant VDB as Postgres (pgvector)
    participant LLM as LLM Client

    User->>API: POST /api/recommend or /api/compare
    API->>Pipe: Pipeline.run(query)
    Pipe->>Guard: input guardrail chain

    alt blocked (injection / heuristics)
        Guard-->>Pipe: block(reason)
        Pipe-->>API: raise InputGuardrailBlocked
        API-->>User: 422 (Vietnamese reason)
    else allow / sanitize
        Guard-->>Pipe: sanitized query

        alt RECOMMEND
            Pipe->>Pipe: UserIntentParser.parse(query)
            Pipe->>Pipe: FilterEngine.extract(query)
            Pipe->>VDB: query(vector, filters)
            VDB-->>Pipe: candidates
            Pipe->>Pipe: CrossEncoderReranker.rerank(candidates)
            Pipe->>Pipe: ProductScorer.score(candidates)
        else COMPARE
            Pipe->>VDB: fetch products (by query or product_ids)
            VDB-->>Pipe: products
            Pipe->>Pipe: SpecAligner.align(products)
            Pipe->>Pipe: ComparisonFormatter.format(aligned)
        end

        Pipe->>Guard: context guardrail (sanitize product text)
        Guard-->>Pipe: sanitized context
        Pipe->>LLM: generate(prompt_with_context)
        LLM-->>Pipe: raw text response
        Pipe->>Pipe: ResponseParser.parse(raw)
        Pipe->>Guard: output guardrail (schema validate + grounding)

        alt valid & grounded
            Guard-->>Pipe: sanitized_payload
        else invalid JSON/schema, or empty after grounding
            Guard-->>Pipe: block(reason)
            Pipe->>Pipe: deterministic fallback (no second LLM call)
        end

        Pipe-->>API: {result, warnings[]}
        API-->>User: 200 JSON Response
    end
```

## Core Layers

### 1. Ingestion (`src/ingestion/`)

Loads raw product data (JSON, CSV), cleans and normalizes it, then splits each product into field-based chunks (description, specs, pros/cons, reviews). Each chunk carries metadata (product_id, brand, category, price) for filtering.

### 2. Embedding (`src/embedding/`)

Converts text chunks into vector embeddings using OpenAI's `text-embedding-3-small` model. Stores vectors in Postgres (pgvector) with an HNSW cosine-similarity index. Supports multi-field embedding for richer retrieval.

### 3. Retrieval (`src/retrieval/`)

Given a user query, the retrieval layer extracts filters from natural language (price range, brand, category), performs hybrid search — semantic (pgvector) fused with BM25 keyword search (Elasticsearch in production, in-memory fallback) via Reciprocal Rank Fusion, with the same filters pre-applied on both branches — computes composite scores (semantic similarity, price match, rating, popularity), and optionally reranks with a cross-encoder. See [Hybrid Retrieval](hybrid-retrieval.md).

### 4. Generation (`src/generation/`)

Takes the retrieved products and user intent, fills a prompt template, and calls the LLM (Claude or GPT) to generate a structured JSON response.

### Guardrails (`src/guardrails/`)

A cross-cutting, non-LLM layer wired into both pipelines at three points: an **input guardrail** rejects/cleans the raw query before retrieval, a **context guardrail** sanitizes retrieved product text before it enters the prompt, and an **output guardrail** validates the LLM's JSON against a schema and grounds every item against retrieved products — falling back to a deterministic response (no second LLM call) on failure instead of erroring out. See [Guardrails](guardrails.md) for the full breakdown.

### 5. Catalog & CDC Sync (`src/catalog/`, `src/sync/`)

The `product_catalog` table (Postgres) is the single source of truth. The CRUD API (`/api/products`) writes only there; Debezium captures row changes from the WAL into Kafka, and two workers (`scripts/sync_worker.py`) consume that single ordered stream to keep the derived indexes fresh: the **indexer** updates the Elasticsearch keyword index, the **embedding worker** updates pgvector — re-embedding only when text-bearing fields changed (price/rating changes are cheap metadata-only updates).

## Orchestration (`src/pipeline/`)

The pipeline layer ties everything together. The `RAGRouter` classifies incoming queries (recommend, compare, info, hybrid) and delegates to the appropriate pipeline. Each pipeline orchestrates the full flow from query to response.

### Service discovery (`src/registry/`)

Separate from the RAG pipeline: on startup, the FastAPI `lifespan` in
`api/app.py` calls `src/registry/client.py:register_if_configured` to
register `{name: "rag-recommend", host, port: <GRPC_PORT>, health:
"http://<host>:<HTTP_PORT>/health"}` with the platform's `service-registry`
(`REGISTRY_URL`), heartbeating every ~10s and deregistering on shutdown.
The *gRPC* port is registered (what the gateway dials); `health` points at
the HTTP port. Registration is skipped entirely if `REGISTRY_URL` is unset,
so the service still runs standalone.

## See Also

- [C4 Model](c4-model.md) — Context, Container, and Component diagrams of the system.
- [Data Flow](data-flow.md) — data formats and storage as they move through ingestion and per-request processing.
- [Hybrid Retrieval](hybrid-retrieval.md) — semantic + BM25 fusion, and how CDC keeps both indexes fresh.
- [Guardrails](guardrails.md) — input/context/output validation, grounding, and the deterministic fallback policy.
