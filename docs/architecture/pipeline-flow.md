# Pipeline Flow

This page describes the detailed data flow through the RAG system, from user query to final response.

## High-Level Overview

Every user query goes through the **RAG Router** first, which classifies the query into one of four types and dispatches it to the appropriate pipeline.

```mermaid
flowchart TD
    Q[User Query] --> R[RAG Router]
    R -->|RECOMMEND| RP[Recommend Pipeline]
    R -->|COMPARE| CP[Compare Pipeline]
    R -->|INFO| IP[Info Lookup]
    R -->|HYBRID| HP[Recommend + Compare]
    RP --> Resp[JSON Response]
    CP --> Resp
    IP --> Resp
    HP --> Resp
```

## Query Classification (RAG Router)

The `RAGRouter` classifies queries using regex pattern matching on Vietnamese and English keywords.

| Query Type | Trigger Keywords | Example |
| ---------- | --------------- | ------- |
| **RECOMMEND** | gợi ý, nên mua, tư vấn, recommend, đề xuất | *"Tư vấn điện thoại dưới 10 triệu"* |
| **COMPARE** | so sánh, compare, vs, tốt hơn, khác nhau | *"So sánh iPhone 15 và Samsung S24"* |
| **INFO** | thông số, giá, specs, cấu hình, review | *"Giá iPhone 15 Pro Max bao nhiêu?"* |
| **HYBRID** | Both recommend + compare patterns matched | *"Nên mua iPhone hay Samsung, so sánh giúp tôi"* |

If no pattern matches, the router defaults to **RECOMMEND**.

**Source:** `src/pipeline/rag_router.py`

---

## Recommend Pipeline

The recommendation pipeline finds products matching the user's intent and generates an LLM-powered explanation.

```mermaid
flowchart LR
    subgraph Intent["1. Parse Intent"]
        Q[Query] --> IP[UserIntentParser]
        IP --> Intent_Out["budget, use_case,\npriorities, brand_pref"]
    end

    subgraph Retrieve["2. Retrieve"]
        Intent_Out --> FE[FilterEngine]
        FE --> Filters["price, brand,\ncategory, rating"]
        Q --> EMB[ProductEmbedder]
        EMB --> Vec[Query Vector]
        Filters --> VS[VectorStore.query]
        Vec --> VS
        VS --> Candidates["top_k × 3 candidates"]
    end

    subgraph Score["3. Score & Rank"]
        Candidates --> SS[SimilarityScorer]
        SS --> PS[ProductScorer]
        PS --> Ranked["Scored + sorted"]
        Ranked --> TopK["Top K products"]
    end

    subgraph Generate["4. Generate"]
        TopK --> PT[Prompt Template]
        PT --> LLM[LLM Client]
        LLM --> RP[ResponseParser]
        RP --> Resp[JSON Response]
    end
```

### Step-by-Step

**Step 1 — Parse User Intent**

The `UserIntentParser` analyzes the query to extract structured intent:

- **budget** — price range (e.g., "dưới 15 triệu" → `price_max: 15_000_000`)
- **use_case** — purpose (gaming, photography, work, etc.)
- **priorities** — what matters most (camera, battery, performance, etc.)
- **brand_pref** — preferred brand if mentioned

**Source:** `src/pipeline/recommend/user_intent_parser.py`

**Step 2 — Filter & Retrieve**

Two things happen in parallel:

1. **FilterEngine** extracts metadata filters from the query (brand, category, price range, minimum rating) using regex patterns on Vietnamese text.
2. **ProductEmbedder** converts the query into a vector using OpenAI `text-embedding-3-small`.

The `ProductRetriever` then queries ChromaDB with both the vector and metadata filters, retrieving `top_k × 3` candidates (over-fetching for the scoring step to narrow down).

**Source:** `src/retrieval/product_retriever.py`, `src/retrieval/filter_engine.py`

**Step 3 — Score & Rank**

Each candidate gets a composite score from `ProductScorer`:

- **Semantic similarity** — cosine distance from the vector search (converted to `1 - distance`)
- **Price match** — how well the product fits the budget
- **Rating** — average user rating
- **Feature match** — overlap between user priorities and product features

Products are sorted by `final_score` descending and truncated to `top_k`.

**Source:** `src/pipeline/recommend/scoring.py`, `src/retrieval/similarity_scorer.py`

**Step 4 — Generate LLM Response**

The top products are formatted into a context string and injected into a prompt template along with the parsed intent. The LLM generates a Vietnamese response explaining why each product fits the user's needs. The `ResponseParser` extracts structured JSON from the LLM output.

**Source:** `src/pipeline/recommend_pipeline.py`, `src/generation/prompt_templates/recommend_prompt.py`

---

## Compare Pipeline

The comparison pipeline retrieves specs for multiple products and generates a detailed analysis.

```mermaid
flowchart LR
    subgraph Extract["1. Get Products"]
        Q[Query] --> EX{product_ids\nprovided?}
        EX -->|Yes| Lookup[Lookup by ID]
        EX -->|No| Search[Retrieve from query]
        Lookup --> Products
        Search --> Products["Product list\n≥ 2 required"]
    end

    subgraph Compare["2. Compare"]
        Products --> COMP[ProductComparator]
        COMP --> SA[SpecAligner]
        SA --> Aligned["Aligned specs table"]
        Aligned --> FMT[ComparisonFormatter]
        FMT --> Table["Markdown table"]
    end

    subgraph Analyze["3. LLM Analysis"]
        Table --> PT[Prompt Template]
        Products --> PT
        PT --> LLM[LLM Client]
        LLM --> RP[ResponseParser]
        RP --> Resp["JSON Response\n(table + analysis)"]
    end
```

### Step-by-Step

**Step 1 — Get Products**

Two paths depending on the API call:

- **With `product_ids`** — directly look up products from the database.
- **Without `product_ids`** — use the `ProductRetriever` to search for products mentioned in the query, then take the top 3.

At least 2 products are required; otherwise the pipeline returns an error.

**Step 2 — Compare Specifications**

The `ProductComparator` orchestrates the comparison:

1. `SpecAligner` normalizes and aligns specifications across products so they share the same set of keys (e.g., "RAM", "Storage", "Battery").
2. `ComparisonFormatter` renders the aligned data as a Markdown table.
3. `ProsConsExtractor` identifies advantages and disadvantages for each product.

**Source:** `src/pipeline/compare/comparator.py`, `src/pipeline/compare/spec_aligner.py`

**Step 3 — LLM Analysis**

The comparison table and product descriptions are injected into a prompt template. The LLM produces a detailed Vietnamese analysis covering strengths, weaknesses, and a final recommendation based on use case. The response includes both the structured table and the narrative analysis.

**Source:** `src/pipeline/compare_pipeline.py`, `src/generation/prompt_templates/compare_prompt.py`

---

## Cross-Cutting Components

### Hybrid Search

`HybridSearch` combines multiple retrieval strategies:

- **Semantic search** — vector similarity via ChromaDB (currently active)
- **Keyword search** — BM25 for exact term matches (planned)
- **Metadata filter** — price, brand, category constraints

Results from all strategies are merged and deduplicated.

**Source:** `src/retrieval/hybrid_search.py`

### Cross-Encoder Reranking

After initial retrieval, the `CrossEncoderReranker` can re-score candidates using a cross-encoder model (`ms-marco-MiniLM-L-6-v2`). Unlike bi-encoders that encode query and document separately, cross-encoders process the (query, document) pair jointly, producing more accurate relevance scores at the cost of speed.

```mermaid
flowchart LR
    C["Initial candidates\n(bi-encoder)"] --> CE["Cross-Encoder\n(query, doc) pairs"]
    CE --> S["Rerank scores"]
    S --> R["Top K reranked"]
```

**Source:** `src/retrieval/reranker.py`

### Guardrails

The `Guardrails` module validates both input and output:

- **Input validation** — checks query length, detects prompt injection attempts
- **Output validation** — ensures LLM responses are well-formed JSON and don't contain hallucinated product data

**Source:** `src/generation/guardrails.py`

### LLM Client

The `LLMClient` provides a unified interface for three providers:

| Provider | Model Example | SDK |
| -------- | ------------- | --- |
| Anthropic | `claude-sonnet-4-6` | `anthropic` |
| OpenAI | `gpt-4o` | `openai` |
| Gemini | `gemini-2.0-flash` | `google-genai` |

The provider is configured in `configs/settings.yaml` and the appropriate API key is resolved automatically via the `PROVIDER_API_KEY_ENV` mapping.

**Source:** `src/generation/llm_client.py`

### Dependency Injection

All components are wired together via factory functions in `api/deps.py`:

```
get_config() → PipelineConfig
get_embedder() → ProductEmbedder
get_vector_store() → VectorStore
get_retriever() → ProductRetriever
get_llm_client() → LLMClient
get_recommend_pipeline() → RecommendPipeline
get_compare_pipeline() → ComparePipeline
```

FastAPI routes call these factories to get fully configured pipeline instances.

**Source:** `api/deps.py`

---

## Data Flow Summary

```mermaid
flowchart TD
    subgraph Ingestion["Data Ingestion (offline)"]
        RAW["Raw product data\n(JSON/CSV)"] --> CLEAN[DataCleaner]
        CLEAN --> CHUNK[Chunker]
        CHUNK --> EMBED[ProductEmbedder]
        EMBED --> STORE["ChromaDB\n(vectors + metadata)"]
    end

    subgraph Runtime["Query Processing (online)"]
        USER["User Query\n(Vietnamese)"] --> GUARD_IN[Guardrails\ninput check]
        GUARD_IN --> ROUTER[RAG Router]
        ROUTER --> PIPELINE["Recommend / Compare\nPipeline"]
        PIPELINE --> GUARD_OUT[Guardrails\noutput check]
        GUARD_OUT --> API["JSON Response"]
    end

    STORE -.->|"vector search"| PIPELINE
```

The system has two phases: **ingestion** (offline, batch) loads product data into the vector store, and **runtime** (online, per-request) processes user queries through the appropriate pipeline.
