# Chi tiết Pipeline

## RAG Router

`RAGRouter` phân loại truy vấn người dùng thành bốn loại bằng cách so khớp regex trên các từ khóa tiếng Việt:

| Loại        | Từ khóa kích hoạt                                    | Pipeline             |
| ----------- | --------------------------------------------------- | -------------------- |
| `RECOMMEND` | "gợi ý", "nên mua", "tư vấn", "recommend"         | RecommendPipeline    |
| `COMPARE`   | "so sánh", "compare", "vs", "tốt hơn"              | ComparePipeline      |
| `INFO`      | "thông số", "giá", "specs", "chi tiết"              | Truy xuất trực tiếp  |
| `HYBRID`    | Khớp cả pattern recommend + compare                  | RecommendPipeline    |

## Recommend Pipeline

```
Query
  → Guardrail đầu vào (normalize → heuristics → injection; block → HTTP 422)
  → UserIntentParser (trích xuất use_case, budget, priorities)
  → FilterEngine (trích xuất brand, category, price range)
  → ProductRetriever (hybrid search + metadata filter)
  → CrossEncoderReranker (tùy chọn, rerank theo độ liên quan)
  → ProductScorer (đa tiêu chí: relevance, review, value, popularity)
  → Guardrail ngữ cảnh (sanitize dữ liệu sản phẩm trước khi vào prompt)
  → LLM (sinh giải thích bằng template recommend_prompt)
  → ResponseParser (trích xuất JSON)
  → Guardrail đầu ra (validate schema + grounding; fallback khi thất bại)
  → Response
```

### Trọng số Scoring

Có thể cấu hình theo từng use case trong `configs/scoring_weights.yaml`:

| Tiêu chí    | Mặc định | Gaming | Photography | Budget |
| ----------- | ------- | ------ | ----------- | ------ |
| Relevance   | 0.35    | 0.40   | 0.40        | 0.25   |
| Review      | 0.25    | 0.20   | 0.30        | 0.20   |
| Value       | 0.25    | 0.20   | 0.15        | 0.40   |
| Popularity  | 0.15    | 0.20   | 0.15        | 0.15   |

## Compare Pipeline

```
Query (tùy chọn nếu đã có product_ids)
  → Guardrail đầu vào (chỉ khi có query; normalize → heuristics → injection; block → HTTP 422)
  → Trích xuất tên sản phẩm từ query (hoặc nhận product_ids, tra cứu qua ProductRepository)
  → ProductRetriever (lấy đầy đủ dữ liệu sản phẩm; cần ≥ 2, nếu không → HTTP 422)
  → SpecAligner (chuẩn hóa tên trường, đối chiếu thông số giữa các sản phẩm)
  → ProductComparator (so sánh theo từng tiêu chí, tìm điểm nổi bật)
  → ComparisonFormatter (sinh bảng markdown)
  → Guardrail ngữ cảnh (sanitize dữ liệu sản phẩm trước khi vào prompt)
  → LLM (sinh phân tích bằng template compare_prompt)
  → ResponseParser (trích xuất JSON)
  → Guardrail đầu ra (validate schema + grounding; fallback khi thất bại)
  → Response
```

## Các thành phần dùng chung (Cross-Cutting)

### Guardrails

Cả hai pipeline ở trên đều chạy ba tầng guardrail không dùng LLM ngay trong luồng: **guardrail đầu vào** trước khi truy xuất, **guardrail ngữ cảnh** trước khi đưa vào prompt, và **guardrail đầu ra** (validate schema + grounding, kèm fallback tất định khi thất bại) trước khi trả phản hồi. Chi tiết đầy đủ: [Guardrail](guardrails.vi.md).

**Nguồn:** `src/guardrails/`

### Hybrid Search

Luồng recommend truy xuất ứng viên bằng `HybridSearch`, hợp nhất hai nhánh qua **Reciprocal Rank Fusion** (`rrf_k = 60`, dựa trên thứ hạng nên không cần hiệu chỉnh thang điểm giữa cosine và BM25):

- **Semantic search** — độ tương đồng vector qua Postgres + pgvector (`ProductRetriever`), với metadata filter đẩy vào mệnh đề SQL `WHERE` (pre-filter).
- **Keyword search (BM25)** — backend cắm thay được (pluggable):
    - **Production** — Elasticsearch (`ESKeywordSearch`, index `product_chunks`), luôn fresh nhờ các CDC sync worker; filter được đẩy vào query ES dưới dạng mệnh đề `bool.filter` (pre-filter, cùng đảm bảo như nhánh SQL).
    - **Fallback cho dev** — snapshot `BM25Index` in-memory build lúc khởi động từ vector store, filter được áp lại bằng Python (post-filter).
    - **Fallback cuối** — semantic-only, nếu không backend keyword nào khả dụng.

Chi tiết đầy đủ, gồm cả cách CDC giữ index fresh và đảm bảo pre-filter vs post-filter: [Truy xuất lai](hybrid-retrieval.vi.md).

**Nguồn:** `src/retrieval/hybrid_search.py`, `src/retrieval/es_keyword_search.py`, `src/retrieval/keyword_search.py`

## Catalog & CDC Sync Pipeline

Dữ liệu sản phẩm có một **source of truth** duy nhất: bảng `product_catalog` (Postgres, `REPLICA IDENTITY FULL`). API CRUD (`POST/PUT/DELETE /api/products`) **chỉ** ghi vào đó — không bao giờ động trực tiếp tới các index tìm kiếm. Thay vào đó, **Debezium** bắt thay đổi row từ WAL (plugin pgoutput, `snapshot.mode: initial`) vào Kafka topic `ragshop.public.product_catalog`, và hai CDC sync worker (`scripts/sync_worker.py --role indexer|embedder`) consume một stream có thứ tự duy nhất để giữ các index dẫn xuất luôn fresh.

```mermaid
flowchart TD
    CRUD["API CRUD sản phẩm\nPOST/PUT/DELETE /api/products"] --> CAT[("product_catalog\nsource of truth")]
    CAT -->|"WAL → Debezium (pgoutput)"| KAFKA["Kafka topic\nragshop.public.product_catalog"]
    KAFKA --> IW["indexer worker\nSearchIndexer"]
    KAFKA --> EW["embedding worker\nEmbeddingSyncer"]
    IW --> ESI[("Elasticsearch\nproduct_chunks (BM25)")]
    EW --> PGV[("Postgres + pgvector\nsemantic index")]
```

- **Indexer worker** (`src/sync/indexer_worker.py`, `SearchIndexer`) → cập nhật index keyword/BM25 Elasticsearch `product_chunks`; mỗi lần áp là upsert/delete idempotent theo chunk id `{product_id}_{chunk_type}`.
- **Embedding worker** (`src/sync/embedding_worker.py`, `EmbeddingSyncer`) → cập nhật index semantic pgvector; chỉ re-embed **khi trường mang text thay đổi**. Thay đổi giá/rating là update **metadata-only** JSONB rẻ (không gọi embedding), và replay snapshot của các row không đổi tốn 0 lần gọi embedding (phát hiện qua `content_hash`).

Delivery là **at-least-once** — offset Kafka chỉ commit sau khi handler áp xong event (`src/sync/runner.py`) — và cả hai handler đều **idempotent**, nên replay luôn hội tụ. Kết quả là eventual consistency: lag chỉ làm kết quả tìm kiếm *trễ*, không bao giờ sai. Xem [Truy xuất lai](hybrid-retrieval.vi.md) và vòng đời CDC ở [Luồng dữ liệu](data-flow.vi.md).

**Nguồn:** `scripts/sync_worker.py`, `src/sync/*.py`, `src/catalog/product_repository.py`, `docker/debezium/product-catalog-connector.json`

## Cấu hình

Toàn bộ cài đặt pipeline được tập trung trong `PipelineConfig` (nạp từ `configs/settings.yaml`):

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

# Truy xuất lai (hybrid)
use_bm25: true
rrf_k: 60
keyword_candidates: 50
keyword_backend: "elasticsearch"   # hoặc "memory" (snapshot in-memory)
es_url: "http://localhost:9200"
es_index: "product_chunks"

# Catalog & CDC sync
kafka_bootstrap: "localhost:9092"
products_topic: "ragshop.public.product_catalog"
catalog_table: "product_catalog"
```
