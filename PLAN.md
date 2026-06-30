# PLAN: RAG Product Recommendation & Comparison

## Tổng quan dự án

Xây dựng hệ thống RAG cho bài toán **gợi ý sản phẩm (Recommend)** và **so sánh sản phẩm (Compare)**.
Người dùng hỏi bằng ngôn ngữ tự nhiên → hệ thống truy xuất dữ liệu sản phẩm → LLM sinh câu trả lời.

---

## Phase 1: Thu thập & Chuẩn hóa dữ liệu (1-2 tuần)

### 1.1 — Xác định nguồn dữ liệu
- [ ] Xác định danh mục sản phẩm (điện thoại, laptop, tai nghe...)
- [ ] Liệt kê nguồn dữ liệu: API, crawl website, CSV, JSON
- [ ] Xác định các trường dữ liệu cần thu thập cho mỗi danh mục

### 1.2 — Xây dựng Data Loader
- [ ] `src/ingestion/product_loader.py` — Đọc dữ liệu sản phẩm từ nhiều format
- [ ] `src/ingestion/review_loader.py` — Đọc và parse review người dùng
- [ ] `src/ingestion/spec_parser.py` — Parse thông số kỹ thuật từ text/HTML

### 1.3 — Chuẩn hóa dữ liệu
- [ ] `src/ingestion/data_cleaner.py` — Làm sạch text, chuẩn hóa đơn vị, giá
- [ ] Tạo **Product Profile** chuẩn (JSON schema thống nhất)
- [ ] Lưu kết quả vào `data/processed/product_profiles.json`

### 1.4 — Cập nhật giá
- [ ] `src/ingestion/price_tracker.py` — Theo dõi và cập nhật giá định kỳ

**Output:** File `data/processed/product_profiles.json` chứa tất cả sản phẩm đã chuẩn hóa.

---

## Phase 2: Chunking & Embedding (1 tuần)

### 2.1 — Chunking thông minh theo field
- [ ] `src/ingestion/chunker.py` — Chia sản phẩm thành chunk theo ngữ cảnh:
  - Chunk mô tả chung (tên + brand + mô tả)
  - Chunk thông số kỹ thuật (specifications)
  - Chunk ưu/nhược điểm (pros/cons)
  - Chunk tóm tắt review (review summary)
- [ ] Mỗi chunk kèm metadata: product_id, brand, category, price, chunk_type

### 2.2 — Tóm tắt Review bằng LLM
- [ ] Gom review theo sản phẩm → LLM tóm tắt 3-5 câu
- [ ] Trích xuất ưu/nhược điểm từ review
- [ ] Lưu vào `data/processed/review_summaries/`

### 2.3 — Tạo Embeddings & Lưu Vector DB
- [ ] `src/embedding/product_embedder.py` — Embedding từng chunk
- [ ] `src/embedding/multi_field_embedder.py` — Embedding riêng theo field
- [ ] `src/embedding/vector_store.py` — Kết nối ChromaDB/Qdrant, tạo collection, index metadata

**Output:** Vector DB đã index toàn bộ sản phẩm, sẵn sàng truy vấn.

---

## Phase 3: Retrieval & Filtering (1 tuần)

### 3.1 — Hybrid Search
- [ ] `src/retrieval/hybrid_search.py` — Kết hợp semantic + keyword + metadata filter

### 3.2 — Filter Engine
- [ ] `src/retrieval/filter_engine.py` — Trích xuất điều kiện lọc từ câu hỏi tự nhiên:
  - "tầm 15 triệu" → price_max: 15000000
  - "của Samsung" → brand: Samsung
  - "đánh giá tốt" → min_rating: 4.0

### 3.3 — Similarity Scoring
- [ ] `src/retrieval/similarity_scorer.py` — Tính điểm tương đồng tổng hợp
- [ ] `src/retrieval/product_retriever.py` — Kết hợp filter + search → top-K sản phẩm

**Output:** Hàm `retrieve(query)` → danh sách sản phẩm phù hợp nhất.

---

## Phase 4: Recommendation Engine (1-2 tuần)

### 4.1 — Phân tích ý định người dùng
- [ ] `src/recommendation/user_intent_parser.py` — Xác định mục đích, ngân sách, ưu tiên

### 4.2 — Scoring sản phẩm
- [ ] `src/recommendation/scoring.py` — Chấm điểm: relevance, review, value, popularity

### 4.3 — Recommend Engine
- [ ] `src/recommendation/recommend_engine.py` — Xếp hạng + chọn top 3-5 + giải thích lý do

### 4.4 — Cá nhân hóa (optional)
- [ ] `src/recommendation/personalization.py` — Dựa trên lịch sử user nếu có

**Output:** Hàm `recommend(query)` → top-K sản phẩm + lý do gợi ý.

---

## Phase 5: Comparison Engine (1 tuần)

### 5.1 — Căn chỉnh thông số
- [ ] `src/comparison/spec_aligner.py` — Map field tương đương, chuẩn hóa đơn vị

### 5.2 — So sánh sản phẩm
- [ ] `src/comparison/comparator.py` — So sánh N sản phẩm, xác định thắng/thua từng tiêu chí

### 5.3 — Trích xuất ưu/nhược
- [ ] `src/comparison/pros_cons_extractor.py` — Dùng LLM phân tích ưu/nhược nổi bật

### 5.4 — Format kết quả
- [ ] `src/comparison/comparison_formatter.py` — Tạo bảng so sánh + phân tích + kết luận

**Output:** Hàm `compare(product_ids)` → bảng so sánh + phân tích + kết luận.

---

## Phase 6: Prompt Engineering & Generation (3-5 ngày)

- [ ] `src/generation/prompt_templates/recommend_prompt.py` — Prompt gợi ý sản phẩm
- [ ] `src/generation/prompt_templates/compare_prompt.py` — Prompt so sánh sản phẩm
- [ ] `src/generation/prompt_templates/review_summary_prompt.py` — Prompt tóm tắt review
- [ ] `src/generation/llm_client.py` — Hỗ trợ nhiều LLM provider
- [ ] `src/generation/response_parser.py` — Parse structured output

---

## Phase 7: Pipeline & Router (3-5 ngày)

- [ ] `src/pipeline/rag_router.py` — Phân loại: RECOMMEND / COMPARE / INFO / HYBRID
- [ ] `src/pipeline/recommend_pipeline.py` — Query → Intent → Filter → Retrieve → Score → LLM
- [ ] `src/pipeline/compare_pipeline.py` — Query → Extract Products → Retrieve → Compare → LLM
- [ ] `src/pipeline/config.py` — Cấu hình pipeline

---

## Phase 8: API Layer (1 tuần)

- [ ] `POST /api/recommend` — Gợi ý sản phẩm
- [ ] `POST /api/compare` — So sánh sản phẩm
- [ ] `POST /api/search` — Tìm kiếm sản phẩm
- [ ] Cache: Redis cho query lặp, kết quả so sánh, embedding cache

---

## Phase 9: Evaluation & Testing (1 tuần)

- [ ] Tạo bộ test 50-100 câu hỏi mẫu + đáp án kỳ vọng
- [ ] Metrics: Relevance, Faithfulness, Completeness, Fairness
- [ ] Unit tests cho tất cả module

---

## Phase 10: Deployment (1 tuần)

- [ ] Docker + Docker Compose (app + vector DB + Redis)
- [ ] Monitoring: log query/response, latency, error rate
- [ ] CI/CD pipeline

---

## Tech Stack

| Component        | Lựa chọn                                      |
|------------------|------------------------------------------------|
| Language         | Python 3.11+                                   |
| API Framework    | FastAPI                                         |
| LLM              | Claude API / GPT-4                              |
| Embedding        | text-embedding-3-small / bge-large-en-v1.5     |
| Vector DB        | ChromaDB (dev) → Qdrant/Pinecone (prod)        |
| Cache            | Redis                                           |
| Database         | PostgreSQL (metadata) + Vector DB (embeddings)  |
| Container        | Docker + Docker Compose                         |
| Testing          | pytest + RAGAS                                  |

---

## Timeline: 8-12 tuần tổng cộng
