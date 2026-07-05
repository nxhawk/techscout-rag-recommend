# Pipeline Details

## RAG Router

The `RAGRouter` classifies user queries into four types using regex pattern matching on Vietnamese keywords:

| Type        | Trigger Keywords                                    | Pipeline             |
| ----------- | --------------------------------------------------- | -------------------- |
| `RECOMMEND` | "gợi ý", "nên mua", "tư vấn", "recommend"         | RecommendPipeline    |
| `COMPARE`   | "so sánh", "compare", "vs", "tốt hơn"              | ComparePipeline      |
| `INFO`      | "thông số", "giá", "specs", "chi tiết"              | Direct retrieval     |
| `HYBRID`    | Both recommend + compare patterns                   | RecommendPipeline    |

## Recommend Pipeline

```
Query
  → UserIntentParser (extract use_case, budget, priorities)
  → FilterEngine (extract brand, category, price range)
  → ProductRetriever (hybrid search + metadata filter)
  → CrossEncoderReranker (optional, rerank by relevance)
  → ProductScorer (multi-criteria: relevance, review, value, popularity)
  → LLM (generate explanation with recommend_prompt template)
  → ResponseParser (extract structured JSON)
  → Response
```

### Scoring Weights

Configurable per use case in `configs/scoring_weights.yaml`:

| Criterion   | Default | Gaming | Photography | Budget |
| ----------- | ------- | ------ | ----------- | ------ |
| Relevance   | 0.35    | 0.40   | 0.40        | 0.25   |
| Review      | 0.25    | 0.20   | 0.30        | 0.20   |
| Value       | 0.25    | 0.20   | 0.15        | 0.40   |
| Popularity  | 0.15    | 0.20   | 0.15        | 0.15   |

## Compare Pipeline

```
Query
  → Extract product names from query (or accept product_ids)
  → ProductRetriever (fetch full product data)
  → SpecAligner (normalize field names, align specs across products)
  → ProductComparator (compare per criterion, find highlights)
  → ComparisonFormatter (generate markdown table)
  → LLM (generate analysis with compare_prompt template)
  → ResponseParser (extract structured JSON)
  → Response
```

## Cross-Cutting Components

### Hybrid Search

The recommend flow retrieves candidates with `HybridSearch`, which fuses two branches with **Reciprocal Rank Fusion** (`rrf_k = 60`, rank-based so cosine and BM25 scores never need calibration):

- **Semantic search** — vector similarity via Postgres + pgvector (`ProductRetriever`), with metadata filters pushed into the SQL `WHERE` clause (pre-filter).
- **Keyword search (BM25)** — pluggable backend:
    - **Production** — Elasticsearch (`ESKeywordSearch`, index `product_chunks`), kept fresh by the CDC sync workers; filters are pushed into the ES query as `bool.filter` clauses (pre-filter, same guarantee as the SQL branch).
    - **Dev fallback** — an in-memory `BM25Index` snapshot built at startup from the vector store, with filters re-applied in Python (post-filter).
    - **Final fallback** — semantic-only, if neither keyword backend is available.

Full details, including CDC freshness and pre-filter vs post-filter guarantees: [Hybrid Retrieval](hybrid-retrieval.md).

**Source:** `src/retrieval/hybrid_search.py`, `src/retrieval/es_keyword_search.py`, `src/retrieval/keyword_search.py`

## Catalog & CDC Sync Pipeline

Product data has a single **source of truth**: the `product_catalog` table (Postgres, `REPLICA IDENTITY FULL`). The CRUD API (`POST/PUT/DELETE /api/products`) writes **only** there — it never touches the search indexes directly. Instead, **Debezium** captures row changes from the WAL (pgoutput plugin, `snapshot.mode: initial`) into the Kafka topic `ragshop.public.product_catalog`, and two CDC sync workers (`scripts/sync_worker.py --role indexer|embedder`) consume that single ordered stream to keep the derived indexes fresh.

```mermaid
flowchart TD
    CRUD["Product CRUD API\nPOST/PUT/DELETE /api/products"] --> CAT[("product_catalog\nsource of truth")]
    CAT -->|"WAL → Debezium (pgoutput)"| KAFKA["Kafka topic\nragshop.public.product_catalog"]
    KAFKA --> IW["indexer worker\nSearchIndexer"]
    KAFKA --> EW["embedding worker\nEmbeddingSyncer"]
    IW --> ESI[("Elasticsearch\nproduct_chunks (BM25)")]
    EW --> PGV[("Postgres + pgvector\nsemantic index")]
```

- **Indexer worker** (`src/sync/indexer_worker.py`, `SearchIndexer`) → updates the Elasticsearch keyword/BM25 index `product_chunks`; every apply is an idempotent upsert/delete keyed by chunk id `{product_id}_{chunk_type}`.
- **Embedding worker** (`src/sync/embedding_worker.py`, `EmbeddingSyncer`) → updates the pgvector semantic index; it re-embeds **only when a text-bearing field changed**. Price/rating changes are cheap **metadata-only** JSONB updates (no embedding call), and snapshot replays of unchanged rows cost zero embedding calls (detected via `content_hash`).

Delivery is **at-least-once** — Kafka offsets are committed only after the handler applied the event (`src/sync/runner.py`) — and both handlers are **idempotent**, so replays converge. The result is eventual consistency: lag makes search results *stale*, never wrong. See [Hybrid Retrieval](hybrid-retrieval.md) and the [Data Flow](data-flow.md#continuous-product-write-data-flow-cdc) CDC lifecycle.

**Source:** `scripts/sync_worker.py`, `src/sync/*.py`, `src/catalog/product_repository.py`, `docker/debezium/product-catalog-connector.json`

## Configuration

All pipeline settings are centralized in `PipelineConfig` (loaded from `configs/settings.yaml`):

```yaml
llm_provider: "gemini"
llm_model: "gemini-2.5-flash"
embedding_provider: "gemini"
embedding_model: "gemini-embedding-001"
embedding_dim: 768
vector_db: "pgvector"
vector_db_url: "postgresql://postgres:postgres@localhost:5432/rag_products"
top_k_retrieve: 20
top_k_recommend: 5

# Hybrid retrieval
use_bm25: true
rrf_k: 60
keyword_candidates: 50
keyword_backend: "elasticsearch"   # or "memory" (in-memory snapshot)
es_url: "http://localhost:9200"
es_index: "product_chunks"

# Catalog & CDC sync
kafka_bootstrap: "localhost:9092"
products_topic: "ragshop.public.product_catalog"
catalog_table: "product_catalog"
```
