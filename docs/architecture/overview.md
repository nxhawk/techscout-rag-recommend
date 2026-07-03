# Architecture Overview

The system follows a standard RAG architecture with four core layers:

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
        EMBED --> VDB[("ChromaDB\nvectors + metadata")]
    end

    subgraph Online["Query Processing (online, per-request)"]
        direction TB
        Q[User Query] --> GIN["Guardrails\n(input check)"]
        GIN --> ROUTER{RAG Router}

        ROUTER -->|RECOMMEND| RI[UserIntentParser]
        RI --> RF[FilterEngine]
        RF --> RR[ProductRetriever]
        RR --> RRK[CrossEncoderReranker]
        RRK --> RSC[ProductScorer]

        ROUTER -->|COMPARE| CX[Extract Products]
        CX --> CR[ProductRetriever]
        CR --> CAL[SpecAligner]
        CAL --> CFM[ComparisonFormatter]

        RSC --> LLM["LLM Client\n(Anthropic / OpenAI / Gemini)"]
        CFM --> LLM
        LLM --> RP[ResponseParser]
        RP --> GOUT["Guardrails\n(output check)"]
        GOUT --> RESP[JSON Response]
    end

    VDB -.->|vector + metadata search| RR
    VDB -.->|vector + metadata search| CR
```

## End-to-End Sequence

The sequence diagram below shows the same online path as a single request timeline, including the `RECOMMEND` vs `COMPARE` branch.

```mermaid
sequenceDiagram
    actor User
    participant API as FastAPI Route
    participant Guard as Guardrails
    participant Router as RAGRouter
    participant Pipe as Recommend/Compare Pipeline
    participant VDB as ChromaDB
    participant LLM as LLM Client

    User->>API: POST /api/recommend or /api/compare
    API->>Guard: validate input
    Guard-->>API: ok

    API->>Router: classify(query)
    Router-->>API: RECOMMEND | COMPARE

    alt RECOMMEND
        API->>Pipe: RecommendPipeline.run(query)
        Pipe->>Pipe: UserIntentParser.parse(query)
        Pipe->>Pipe: FilterEngine.extract(query)
        Pipe->>VDB: query(vector, filters)
        VDB-->>Pipe: candidates
        Pipe->>Pipe: CrossEncoderReranker.rerank(candidates)
        Pipe->>Pipe: ProductScorer.score(candidates)
    else COMPARE
        API->>Pipe: ComparePipeline.run(query)
        Pipe->>VDB: fetch products (by query or product_ids)
        VDB-->>Pipe: products
        Pipe->>Pipe: SpecAligner.align(products)
        Pipe->>Pipe: ComparisonFormatter.format(aligned)
    end

    Pipe->>LLM: generate(prompt_with_context)
    LLM-->>Pipe: raw text response
    Pipe->>Pipe: ResponseParser.parse(raw)
    Pipe-->>API: structured result

    API->>Guard: validate output
    Guard-->>API: ok
    API-->>User: JSON Response
```

## Core Layers

### 1. Ingestion (`src/ingestion/`)

Loads raw product data (JSON, CSV), cleans and normalizes it, then splits each product into field-based chunks (description, specs, pros/cons, reviews). Each chunk carries metadata (product_id, brand, category, price) for filtering.

### 2. Embedding (`src/embedding/`)

Converts text chunks into vector embeddings using OpenAI's `text-embedding-3-small` model. Stores vectors in ChromaDB with cosine similarity indexing. Supports multi-field embedding for richer retrieval.

### 3. Retrieval (`src/retrieval/`)

Given a user query, the retrieval layer extracts filters from natural language (price range, brand, category), performs hybrid search (semantic + metadata), computes composite scores (semantic similarity, price match, rating, popularity), and optionally reranks with a cross-encoder.

### 4. Generation (`src/generation/`)

Takes the retrieved products and user intent, fills a prompt template, and calls the LLM (Claude or GPT) to generate a structured JSON response. Includes guardrails for input validation and output safety checks.

## Orchestration (`src/pipeline/`)

The pipeline layer ties everything together. The `RAGRouter` classifies incoming queries (recommend, compare, info, hybrid) and delegates to the appropriate pipeline. Each pipeline orchestrates the full flow from query to response.

## See Also

- [C4 Model](c4-model.md) — Context, Container, and Component diagrams of the system.
- [Data Flow](data-flow.md) — data formats and storage as they move through ingestion and per-request processing.
