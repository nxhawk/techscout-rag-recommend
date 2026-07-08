# PLAN: RAG Product Recommendation & Comparison

## Tổng quan dự án

Xây dựng hệ thống RAG cho bài toán **gợi ý sản phẩm (Recommend)** và **so sánh sản phẩm (Compare)**.
Người dùng hỏi bằng ngôn ngữ tự nhiên (tiếng Việt) → hệ thống truy xuất dữ liệu sản phẩm từ vector DB → LLM sinh câu trả lời theo ngữ cảnh.

Hai pipeline chính:

- **Recommend**: Query → Intent Parser → Filter → Retrieve → Rerank → Score → LLM → Response
- **Compare**: Query → Extract Products → Retrieve Specs → Align → Compare → LLM → Response

> **Chú thích trạng thái:** `[x]` đã hoàn thành · `[~]` khung có sẵn / cần hoàn thiện thêm · `[ ]` chưa làm.
> Cấu trúc thư mục chuẩn được mô tả trong `CLAUDE.md` (đây là nguồn tham chiếu chính).

---

## Phase 0: Crawler — Thu thập dữ liệu thô ✅

> Module `src/crawler/` được bổ sung so với kế hoạch ban đầu: thu thập raw data từ các sàn TMĐT một cách "lịch sự" (tôn trọng robots.txt, rate limit, retry).

### 0.1 — Hạ tầng crawler

- [x] `src/crawler/config.py` — `CrawlerConfig` / `SourceConfig` đọc từ `configs/crawler.yaml`
- [x] `src/crawler/http_client.py` — httpx client: retry (tenacity) + rate limit + robots
- [x] `src/crawler/rate_limiter.py` — delay lịch sự giữa các request
- [x] `src/crawler/robots.py` — kiểm tra robots.txt
- [x] `src/crawler/parser.py` — helper BeautifulSoup (price/rating/text)
- [x] `src/crawler/models.py` — dataclass `CrawledProduct` / `CrawlResult`
- [x] `src/crawler/storage.py` — lưu raw output vào `data/raw/crawled/`
- [x] `src/crawler/exceptions.py` — exception riêng cho crawler
- [x] `src/crawler/pipeline.py` — `CrawlPipeline`: spider → product → store

### 0.2 — Spiders (mỗi nguồn một spider)

- [x] `src/crawler/spiders/base_spider.py` — `BaseSpider` (hook list + detail)
- [x] `src/crawler/spiders/tgdd_spider.py` — thegioididong.com
- [x] `src/crawler/spiders/cellphones_spider.py` — cellphones.com.vn

**Output:** Raw JSON trong `data/raw/crawled/{tgdd,cellphones}/` (đã có `latest.json` + snapshot theo timestamp).

---

## Phase 1: Thu thập & Chuẩn hóa dữ liệu ✅

### 1.1 — Xác định nguồn dữ liệu

- [x] Xác định danh mục sản phẩm (`configs/product_categories.yaml`)
- [x] Liệt kê nguồn dữ liệu: crawl website, CSV, JSON
- [x] Xác định các trường dữ liệu cần thu thập cho mỗi danh mục

### 1.2 — Data Loader

- [x] `src/ingestion/product_loader.py` — Đọc dữ liệu sản phẩm từ JSON/CSV
- [x] `src/ingestion/review_loader.py` — Đọc và parse review người dùng
- [x] `src/ingestion/spec_parser.py` — Parse thông số kỹ thuật từ text/HTML

### 1.3 — Chuẩn hóa dữ liệu

- [x] `src/ingestion/data_cleaner.py` — Làm sạch text, chuẩn hóa đơn vị, giá
- [x] Product Profile chuẩn (schema thống nhất)

### 1.4 — Cập nhật giá

- [x] `src/ingestion/price_tracker.py` — Theo dõi và cập nhật giá định kỳ

**Output:** Dữ liệu sản phẩm đã chuẩn hóa, sẵn sàng cho chunking/embedding.

---

## Phase 2: Chunking & Embedding ✅

### 2.1 — Chunking theo field

- [x] `src/ingestion/chunker.py` — Chia sản phẩm thành chunk theo ngữ cảnh (mô tả chung, specifications, pros/cons, review summary) kèm metadata: product_id, brand, category, price, chunk_type

### 2.2 — Tóm tắt Review bằng LLM

- [x] Prompt tóm tắt review: `src/generation/prompt_templates/review_summary_prompt.py`
- [~] Pipeline gom review theo sản phẩm → LLM tóm tắt (prompt sẵn sàng; batch summarize offline chưa hoàn thiện)

### 2.3 — Tạo Embeddings & Lưu Vector DB

- [x] `src/embedding/product_embedder.py` — Embedding từng chunk (OpenAI)
- [x] `src/embedding/multi_field_embedder.py` — Embedding riêng theo field
- [x] `src/embedding/vector_store.py` — **PostgreSQL + pgvector** (HNSW, cosine), kết nối qua `DATABASE_URL` / `vector_db_url`

**Output:** Vector DB đã index toàn bộ sản phẩm, sẵn sàng truy vấn.

---

## Phase 3: Retrieval & Filtering ✅

### 3.1 — Hybrid Search

- [~] `src/retrieval/hybrid_search.py` — Kết hợp semantic + keyword + metadata filter (khung có sẵn)

### 3.2 — Filter Engine

- [x] `src/retrieval/filter_engine.py` — Trích xuất điều kiện lọc từ câu hỏi tự nhiên
  ("tầm 15 triệu" → price_max; "của Samsung" → brand; "đánh giá tốt" → min_rating)

### 3.3 — Scoring & Reranking

- [x] `src/retrieval/similarity_scorer.py` — Điểm tương đồng tổng hợp
- [x] `src/retrieval/reranker.py` — Cross-encoder reranking
- [x] `src/retrieval/product_retriever.py` — Kết hợp filter + search → top-K sản phẩm

**Output:** `ProductRetriever.retrieve(query)` → danh sách sản phẩm phù hợp nhất.

---

## Phase 4: Recommendation Engine ✅

> Logic gợi ý nằm trong `src/pipeline/recommend/` (đúng theo cấu trúc `CLAUDE.md`).

### 4.1 — Phân tích ý định người dùng

- [x] `src/pipeline/recommend/user_intent_parser.py` — Xác định mục đích, ngân sách, ưu tiên (`UserIntent`)

### 4.2 — Scoring sản phẩm

- [x] `src/pipeline/recommend/scoring.py` — `ProductScorer`: relevance, review, value, popularity

### 4.3 — Recommend Engine

- [x] `src/pipeline/recommend/engine.py` — `RecommendEngine`: xếp hạng + chọn top 3-5 + lý do

### 4.4 — Cá nhân hóa (optional)

- [x] `src/pipeline/recommend/personalization.py` — Dựa trên lịch sử user nếu có

**Output:** `RecommendEngine` → top-K sản phẩm + lý do gợi ý.

---

## Phase 5: Comparison Engine ✅

> Logic so sánh nằm trong `src/pipeline/compare/`.

### 5.1 — Căn chỉnh thông số

- [x] `src/pipeline/compare/spec_aligner.py` — `SpecAligner`: map field tương đương, chuẩn hóa đơn vị

### 5.2 — So sánh sản phẩm

- [x] `src/pipeline/compare/comparator.py` — `ProductComparator`: so sánh N sản phẩm, xác định thắng/thua từng tiêu chí

### 5.3 — Trích xuất ưu/nhược

- [x] `src/pipeline/compare/pros_cons_extractor.py` — Dùng LLM phân tích ưu/nhược nổi bật

### 5.4 — Format kết quả

- [x] `src/pipeline/compare/formatter.py` — `ComparisonFormatter`: bảng so sánh + phân tích + kết luận

**Output:** `ProductComparator` → bảng so sánh + phân tích + kết luận.

---

## Phase 6: Prompt Engineering & Generation ✅

- [x] `src/generation/prompt_templates/recommend_prompt.py` — `SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE`
- [x] `src/generation/prompt_templates/compare_prompt.py`
- [x] `src/generation/prompt_templates/review_summary_prompt.py`
- [x] `src/generation/llm_client.py` — Multi-provider (Anthropic, OpenAI, Gemini)
- [x] `src/generation/response_parser.py` — Parse JSON từ output LLM
- [x] `src/guardrails/` — Guardrail input/context/output không dùng LLM (xem `GUARDRAIL_PLAN.md`); `src/generation/guardrails.py` cũ giữ lại nhưng không còn được dùng

---

## Phase 7: Pipeline & Router ✅

- [x] `src/pipeline/rag_router.py` — Phân loại query: RECOMMEND / COMPARE / INFO / HYBRID
- [x] `src/pipeline/recommend_pipeline.py` — `RecommendPipeline` end-to-end
- [x] `src/pipeline/compare_pipeline.py` — `ComparePipeline` end-to-end
- [x] `src/pipeline/config.py` — `PipelineConfig` (load từ `configs/settings.yaml`)

---

## Phase 8: API Layer ✅

- [x] `api/app.py` — FastAPI entry point
- [x] `api/schemas.py` — Pydantic request/response models
- [x] `api/deps.py` — Factory DI (`get_retriever()`, `get_llm_client()`, ...)
- [x] `POST /api/recommend` — `api/routes/recommend.py`
- [x] `POST /api/compare` — `api/routes/compare.py`
- [x] `POST /api/search` — `api/routes/search.py`
- [x] Middleware: `api/middleware/rate_limit.py`, `api/middleware/error_handler.py`
- [~] Cache: `src/utils/cache.py` (Redis provisioned trong Docker Compose; wiring cache đầy đủ chưa hoàn thiện)

---

## Phase 9: Evaluation & Testing ✅

- [x] `evaluation/test_case/test_cases_recommend.json`, `evaluation/test_case/test_cases_compare.json` — Bộ test case
- [x] `evaluation/eval_recommend.py`, `evaluation/eval_compare.py`
- [x] Unit tests: `tests/unit/ingestion/test_chunker.py`, `retrieval/test_filter_engine.py`, `pipeline/test_rag_router.py` (+ `tests/test_crawler.py`)
- [x] `tests/conftest.py` — fixtures dùng chung; `tests/integration/` sẵn khung
- [~] Mở rộng bộ test 50-100 câu + metrics (Relevance, Faithfulness, Completeness, Fairness)

---

## Phase 10: Deployment & Ops ✅

- [x] `docker/Dockerfile` + `docker/docker-compose.yml` (app + Postgres/pgvector + Redis)
- [x] Scripts CLI: `scripts/crawl.py`, `scripts/ingest.py`, `scripts/seed.py`
- [x] Logging: `src/utils/logger.py` (+ `src/utils/helpers.py`)
- [x] CI/CD: `.github/workflows/` (ruff, mypy, pytest, bandit, gitleaks, pip-audit, codeql, trivy, docs)
- [x] Docs: MkDocs Material song ngữ EN/VI (`docs/`, `mkdocs.yml`, i18n qua `mkdocs-static-i18n`)
- [~] Monitoring: log query/response, latency, error rate (cơ bản; chưa có dashboard)

---

## Tech Stack

| Component     | Lựa chọn                                            |
| ------------- | --------------------------------------------------- |
| Language      | Python 3.11+                                         |
| Package Mgr   | uv                                                  |
| API Framework | FastAPI + uvicorn                                   |
| LLM           | Anthropic Claude / OpenAI GPT / Google Gemini       |
| Embedding     | OpenAI `text-embedding-3-small`                     |
| Vector DB     | PostgreSQL + pgvector (HNSW, cosine)                |
| Crawling      | httpx + BeautifulSoup + lxml + tenacity             |
| Cache         | Redis                                               |
| Container     | Docker + Docker Compose                             |
| Testing       | pytest                                              |
| Docs          | MkDocs Material (song ngữ EN/VI)                    |

---

## Ghi chú kỹ thuật

- **Vector DB đã migrate từ ChromaDB → PostgreSQL + pgvector** (HNSW, cosine). Truy cập qua `src/embedding/vector_store.py`, connection qua `DATABASE_URL` hoặc `vector_db_url` trong `configs/settings.yaml`.
- **Imports**: luôn dùng absolute từ project root (vd `from src.retrieval.filter_engine import FilterEngine`).
- Các module `src/recommendation/` và `src/comparison/` là bản cũ (legacy) — code đang chạy dùng phiên bản trong `src/pipeline/recommend/` và `src/pipeline/compare/` (được wire qua `api/deps.py`).

## Trạng thái tổng quan

Toàn bộ 11 phase (0-10) đã có khung code chạy được: crawler → ingestion → embedding → retrieval → recommend/compare pipeline → generation → router → API → tests → deployment. Phần còn cần hoàn thiện chủ yếu là: hybrid search, batch review summarization, tích hợp Redis cache đầy đủ, mở rộng bộ eval và monitoring.
