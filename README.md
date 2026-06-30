# RAG Product Recommendation & Comparison

Hệ thống gợi ý và so sánh sản phẩm sử dụng **RAG (Retrieval-Augmented Generation)**. Người dùng hỏi bằng ngôn ngữ tự nhiên, hệ thống truy xuất dữ liệu sản phẩm từ vector database, sau đó dùng LLM để sinh câu trả lời có ngữ cảnh.

## Tính năng chính

- **Gợi ý sản phẩm** — Phân tích ý định người dùng (ngân sách, mục đích, ưu tiên) → truy xuất sản phẩm phù hợp → xếp hạng → LLM giải thích lý do gợi ý.
- **So sánh sản phẩm** — Căn chỉnh thông số giữa các sản phẩm → so sánh từng tiêu chí → LLM phân tích ưu/nhược và kết luận.
- **Tìm kiếm thông minh** — Hybrid search (semantic + keyword + metadata filter) với cross-encoder reranking.
- **Đa ngôn ngữ** — Hỗ trợ tiếng Việt cho cả query lẫn response.

## Tech Stack

| Component   | Lựa chọn                                   |
| ----------- | ------------------------------------------- |
| Language    | Python 3.11+                                |
| Package Mgr | [uv](https://docs.astral.sh/uv/)          |
| API         | FastAPI                                     |
| LLM         | Claude API / OpenAI GPT                     |
| Embedding   | text-embedding-3-small                      |
| Vector DB   | ChromaDB (dev) → Qdrant (prod)              |
| Cache       | Redis                                       |
| Container   | Docker + Docker Compose                     |
| Testing     | pytest                                      |

## Quick Start

```bash
# 1. Cài uv (nếu chưa có)
# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone và cài đặt dependencies
git clone <repo-url>
cd rag-product-recommend
uv sync

# 3. Cấu hình API keys
cp .env.example .env
# Sửa .env: ANTHROPIC_API_KEY, OPENAI_API_KEY

# 4. Ingest dữ liệu mẫu
uv run python scripts/ingest.py

# 5. Chạy API server
uv run uvicorn api.app:app --reload

# 6. Chạy tests
uv run pytest tests/
```

## API Endpoints

| Method | Endpoint         | Mô tả              |
| ------ | ---------------- | ------------------- |
| POST   | `/api/recommend` | Gợi ý sản phẩm     |
| POST   | `/api/compare`   | So sánh sản phẩm    |
| POST   | `/api/search`    | Tìm kiếm sản phẩm  |
| GET    | `/health`        | Health check        |

**Ví dụ request:**

```bash
curl -X POST http://localhost:8000/api/recommend \
  -H "Content-Type: application/json" \
  -d '{"query": "Điện thoại chụp ảnh đẹp tầm 15 triệu", "top_k": 3}'
```

## Cấu trúc dự án

```
rag-product-recommend/
├── pyproject.toml              # Dependencies (thay thế requirements.txt)
├── uv.lock                     # Lockfile (tương tự package-lock.json)
├── .env                        # API keys (không commit)
│
├── src/                        # Core business logic
│   ├── ingestion/              # Thu thập & chuẩn hóa dữ liệu
│   │   ├── product_loader.py   #   Đọc data từ JSON/CSV
│   │   ├── review_loader.py    #   Đọc review người dùng
│   │   ├── data_cleaner.py     #   Làm sạch, chuẩn hóa
│   │   ├── spec_parser.py      #   Parse thông số kỹ thuật
│   │   ├── chunker.py          #   Field-based chunking
│   │   └── price_tracker.py    #   Theo dõi giá
│   │
│   ├── embedding/              # Embedding & Vector DB
│   │   ├── product_embedder.py #   Text → vector (OpenAI)
│   │   ├── multi_field_embedder.py  # Embedding riêng theo field
│   │   └── vector_store.py     #   ChromaDB/Qdrant CRUD
│   │
│   ├── retrieval/              # Truy xuất sản phẩm
│   │   ├── product_retriever.py #  Kết hợp filter + search
│   │   ├── hybrid_search.py    #   Semantic + keyword search
│   │   ├── filter_engine.py    #   Trích xuất filter từ NL query
│   │   ├── similarity_scorer.py #  Tính điểm tổng hợp
│   │   └── reranker.py         #   Cross-encoder reranking
│   │
│   ├── generation/             # LLM generation
│   │   ├── llm_client.py       #   Multi-provider LLM client
│   │   ├── response_parser.py  #   Parse JSON từ LLM output
│   │   ├── guardrails.py       #   Input/output validation
│   │   └── prompt_templates/   #   Prompt cho từng use case
│   │       ├── recommend_prompt.py
│   │       ├── compare_prompt.py
│   │       └── review_summary_prompt.py
│   │
│   ├── pipeline/               # Orchestration
│   │   ├── rag_router.py       #   Phân loại query → pipeline
│   │   ├── config.py           #   Pipeline configuration
│   │   ├── recommend_pipeline.py #  E2E recommendation flow
│   │   ├── compare_pipeline.py #   E2E comparison flow
│   │   ├── recommend/          #   Recommendation logic
│   │   │   ├── engine.py       #     Recommendation engine
│   │   │   ├── user_intent_parser.py  # Parse ý định người dùng
│   │   │   ├── scoring.py      #     Multi-criteria scoring
│   │   │   └── personalization.py #   User history boost
│   │   └── compare/            #   Comparison logic
│   │       ├── comparator.py   #     So sánh N sản phẩm
│   │       ├── spec_aligner.py #     Căn chỉnh thông số
│   │       ├── formatter.py    #     Format output
│   │       └── pros_cons_extractor.py
│   │
│   └── utils/                  # Tiện ích
│       ├── logger.py
│       ├── cache.py
│       └── helpers.py
│
├── api/                        # API layer (FastAPI)
│   ├── app.py                  #   FastAPI entry point
│   ├── schemas.py              #   Request/Response models
│   ├── deps.py                 #   Dependency injection
│   ├── routes/
│   │   ├── recommend.py
│   │   ├── compare.py
│   │   └── search.py
│   └── middleware/
│       ├── rate_limit.py       #   Rate limiting
│       └── error_handler.py    #   Error handling
│
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── unit/                   # Unit tests
│   └── integration/            # Integration tests
│
├── evaluation/                 # Đánh giá chất lượng RAG
│   ├── eval_recommend.py
│   ├── eval_compare.py
│   └── test_cases.json
│
├── scripts/                    # CLI scripts
│   ├── ingest.py               #   Ingest data vào vector store
│   └── seed.py                 #   Seed sample data
│
├── configs/
│   ├── settings.yaml           # Main config
│   ├── product_categories.yaml # Danh mục + required fields
│   └── scoring_weights.yaml    # Scoring weights theo use case
│
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
│
└── data/
    ├── raw/products/           # Dữ liệu gốc
    ├── processed/              # Dữ liệu đã chuẩn hóa
    └── embeddings/             # ChromaDB persist (gitignored)
```

## RAG Pipeline Flow

```
User Query
    │
    ▼
┌─────────────┐
│  RAG Router  │ ── Phân loại: RECOMMEND / COMPARE / INFO
└─────┬───────┘
      │
      ├── RECOMMEND ──────────────────────────┐
      │   Intent Parser → Filter → Retrieve   │
      │   → Rerank → Score → LLM → Response   │
      │                                        │
      └── COMPARE ────────────────────────────┐│
          Extract Products → Retrieve Specs   ││
          → Align → Compare → LLM → Response  ││
                                               ▼▼
                                          JSON Response
```

## Development

```bash
# Thêm dependency
uv add <package>

# Thêm dev dependency
uv add --group dev <package>

# Chạy bất kỳ command nào trong venv
uv run <command>

# Docker
cd docker
docker compose up --build
```

## Chi tiết kế hoạch

Xem [PLAN.md](./PLAN.md) để biết roadmap chi tiết từng phase.

## License

MIT
