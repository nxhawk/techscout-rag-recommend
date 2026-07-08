# Kế hoạch triển khai Unit Test & Integration Test

> Tài liệu kế hoạch nội bộ. Code, tên test, fixture: tiếng Anh (theo CLAUDE.md).

## 1. Hiện trạng

**Đã có:**

| Hạng mục | Trạng thái |
|---|---|
| `tests/conftest.py` | 2 fixtures: `sample_product`, `sample_products` |
| `tests/test_crawler.py` | Khá đầy đủ (parser, spider, config, review, discovery) |
| `tests/unit/` | **124 unit test**, tổ chức theo domain mirror `src/` + `api/` (`api/`, `embedding/`, `guardrails/`, `ingestion/`, `pipeline/`, `retrieval/`, `sync/`, `utils/`) |
| `tests/unit/api/conftest.py` | Fixture `client` dùng chung cho route/metrics tests |
| `tests/integration/` | **Rỗng** (chỉ có `__init__.py`) |

**Thiếu:**

- `pytest-cov`, `pytest-asyncio`, `respx` chưa có trong dev deps (CI cài `pytest-cov` qua flag riêng).
- Không có cấu hình pytest trong `pyproject.toml` (testpaths, markers).
- Chưa có test cho: ingestion (trừ chunker), embedding, retrieval (trừ filter_engine), generation, pipeline (trừ router), api middleware/deps, utils.
- Chưa có mocking strategy cho 3 external services: LLM APIs (Anthropic/OpenAI/Gemini), Postgres+pgvector, HTTP crawling.

**Ràng buộc từ CI (`ci.yml`):** test chạy trên Python 3.11 + 3.12, có sẵn service `pgvector/pgvector:pg16` với `DATABASE_URL`, API keys là placeholder (`test-key`) → **test không được gọi API thật, không cần secret thật**.

---

## 2. Nguyên tắc chung

1. **Unit test không chạm network, không chạm DB.** Mock/fake mọi external dependency.
2. **Integration test được dùng Postgres** (CI có service pgvector), nhưng vẫn **không gọi LLM/embedding API thật** — dùng fake provider.
3. Mọi thay đổi phải pass: `uvx ruff check .`, `uv run pytest tests/`, `uvx bandit -r src api scripts -ll -ii -s B608`.
4. Thêm dependency chỉ qua `uv add --group dev <pkg>`, sau đó `uv lock`.
5. Test names, docstrings, comments: tiếng Anh. Dữ liệu mẫu (tên sản phẩm, query): tiếng Việt cho sát thực tế (`"điện thoại pin trâu dưới 10 triệu"`).

**Chiến lược mock theo từng external service:**

| External service | Điểm inject | Cách mock |
|---|---|---|
| LLM (Anthropic/OpenAI/Gemini) | `BaseLLMProvider` + `register_llm_provider` trong `src/generation/llm_client.py` | Viết `FakeLLMProvider` trả JSON cố định; đăng ký qua registry hoặc inject vào `LLMClient` |
| Embedding (OpenAI/Gemini) | Provider trong `src/embedding/product_embedder.py` | `FakeEmbedder` trả vector cố định (vd. hash → vector 8 chiều) |
| Postgres + pgvector | `VectorStore` (`src/embedding/vector_store.py`), constructor injection qua `api/deps.py` | Unit: `FakeVectorStore` (in-memory dict + cosine). Integration: Postgres thật qua `DATABASE_URL` |
| HTTP crawling | `HttpClient` (`src/crawler/http_client.py`, dùng httpx) | `respx` mock httpx routes |
| FastAPI dependencies | Factory functions trong `api/deps.py` | `app.dependency_overrides[get_recommend_pipeline] = ...` |

---

## 3. Giai đoạn 0 — Nền tảng (làm trước tiên)

### 3.1. Thêm dev dependencies

```bash
uv add --group dev pytest-cov pytest-asyncio respx
uv lock
uvx pip-audit   # kiểm tra sau khi thay đổi deps
```

### 3.2. Cấu hình pytest trong `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: tests that need Postgres (DATABASE_URL) or full app wiring",
]
```

### 3.3. Cấu trúc `tests/` (đã áp dụng)

Unit test mirror layout production. Cấu trúc hiện tại:

```
tests/
├── conftest.py                  # shared fixtures (sample_product, sample_products)
├── unit/
│   ├── api/
│   │   ├── conftest.py          # shared TestClient + dependency override cleanup
│   │   ├── test_metrics.py
│   │   ├── test_schemas.py
│   │   └── routes/
│   │       ├── test_compare.py
│   │       ├── test_products.py
│   │       └── test_recommend.py
│   ├── embedding/
│   ├── guardrails/
│   ├── ingestion/
│   ├── pipeline/
│   ├── retrieval/
│   ├── sync/
│   └── utils/
└── integration/                 # pg fixtures, TestClient with overrides (planned)
    ├── test_vector_store_pg.py
    ├── test_api_recommend.py
    ├── test_api_compare.py
    ├── test_api_search.py
    └── test_pipeline_e2e.py
```

**Việc còn lại (nền tảng):**

- Di chuyển `tests/test_crawler.py` → `tests/unit/crawler/` (khi dọn trùng lặp).
- Xóa bản trùng ở root nếu còn: `tests/test_chunker.py`, `tests/test_filter_engine.py`, `tests/test_router.py`.

### 3.4. Mở rộng `tests/conftest.py` — fakes dùng chung

```python
"""Shared test fixtures and fakes."""
import pytest


class FakeEmbedder:
    """Deterministic embedder: no network calls."""

    dim = 8

    def embed(self, text: str) -> list[float]:
        seed = sum(ord(c) for c in text)
        return [((seed * (i + 1)) % 100) / 100 for i in range(self.dim)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class FakeLLMProvider:
    """Returns canned Vietnamese responses without hitting any API."""

    def __init__(self, response: str = '{"recommendations": []}'):
        self.response = response
        self.calls: list[dict] = []

    def setup(self, api_key: str) -> None: ...

    def generate(self, prompt, system_prompt="", max_tokens=2048, **kwargs) -> str:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return self.response


class FakeVectorStore:
    """In-memory stand-in for Postgres/pgvector."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    def add_documents(self, ids, embeddings, metadatas, documents):
        for i, doc_id in enumerate(ids):
            self.docs[doc_id] = {
                "embedding": embeddings[i],
                "metadata": metadatas[i],
                "document": documents[i],
            }

    def query(self, query_embedding, n_results=10, where=None):
        # cosine similarity over self.docs, apply `where` filter on metadata
        ...


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


@pytest.fixture
def fake_llm():
    return FakeLLMProvider()


@pytest.fixture
def fake_vector_store():
    return FakeVectorStore()
```

Giữ nguyên `sample_product` / `sample_products`, bổ sung: `sample_reviews`, `sample_crawled_product`, `sample_query_vi` (các query tiếng Việt tiêu biểu cho recommend/compare/search).

---

## 4. Giai đoạn 1 — Unit tests (theo thứ tự ưu tiên)

Ưu tiên theo nguyên tắc: **logic thuần túy trước (dễ test, ROI cao) → adapter có mock sau**.

### 4.1. `src/generation/` — ưu tiên cao nhất (chưa có test, rủi ro cao)

| File test | Đối tượng | Test cases chính |
|---|---|---|
| `test_response_parser.py` | `response_parser.py` | JSON hợp lệ; JSON bọc trong ```json fence; JSON lẫn text thừa; JSON hỏng → fallback/raise; thiếu field; unicode tiếng Việt |
| `test_guardrails.py` | `guardrails.py` | Input hợp lệ pass; query rỗng/quá dài; prompt injection patterns; output validation (schema sai, nội dung cấm) |
| `test_llm_client.py` | `llm_client.py` | `register_llm_provider` + `available_llm_providers`; chọn provider theo config; key rotation khi nhiều key; retry khi rate-limit (mock SDK exception); `FakeLLMProvider` nhận đúng system_prompt/max_tokens |
| `test_prompt_templates.py` | `prompt_templates/*` | `SYSTEM_PROMPT`/`USER_PROMPT_TEMPLATE` format không vỡ với product data thật; đầu ra chứa tiếng Việt; escape ký tự đặc biệt trong tên sản phẩm |

### 4.2. `src/retrieval/`

| File test | Đối tượng | Test cases chính |
|---|---|---|
| `test_filter_engine.py` | (đã có, mở rộng) | Trích xuất price range từ "dưới 10 triệu", "từ 5 đến 8tr", "khoảng 15 củ"; brand, category, RAM/storage; query không có filter |
| `test_similarity_scorer.py` | `similarity_scorer.py` | Composite score đúng công thức + weights từ `scoring_weights.yaml`; biên: rating 0, review_count 0; score nằm trong [0,1] |
| `test_hybrid_search.py` | `hybrid_search.py` | Kết hợp semantic + keyword đúng trọng số (dùng `fake_vector_store`); keyword không match; dedupe kết quả |
| `test_reranker.py` | `reranker.py` | Thứ tự sau rerank; top_k cắt đúng; input rỗng |
| `test_product_retriever.py` | `product_retriever.py` | Filter + search phối hợp; filter loại hết kết quả → trả rỗng, không crash |

### 4.3. `src/pipeline/`

| File test | Đối tượng | Test cases chính |
|---|---|---|
| `test_rag_router.py` | (đã có, mở rộng) | Query so sánh "A hay B tốt hơn" → compare; "tư vấn..." → recommend; query mơ hồ → default |
| `test_user_intent_parser.py` | `recommend/user_intent_parser.py` | Parse use-case (gaming/pin/camera), budget, số lượng gợi ý từ query tiếng Việt |
| `test_scoring.py` | `recommend/scoring.py` | Multi-criteria scoring; weights hợp lệ; tie-break ổn định |
| `test_personalization.py` | `recommend/personalization.py` | Có/không có user history; history rỗng không đổi kết quả |
| `test_spec_aligner.py` | `compare/spec_aligner.py` | Align spec cùng key khác đơn vị ("8 GB" vs "8GB"); spec chỉ có ở 1 sản phẩm; specs rỗng |
| `test_comparator.py` | `compare/comparator.py` | So sánh 2 sản phẩm (dùng `sample_products`); >2 sản phẩm; 1 sản phẩm → lỗi rõ ràng |
| `test_formatter.py` + `test_pros_cons_extractor.py` | `compare/` | Format bảng so sánh; extract pros/cons từ review data |
| `test_recommend_pipeline.py` | `recommend_pipeline.py` | End-to-end với fakes (fake retriever + `FakeLLMProvider`): query → response đúng schema; retriever trả rỗng → thông báo tiếng Việt hợp lý |
| `test_compare_pipeline.py` | `compare_pipeline.py` | Tương tự với compare flow |
| `test_pipeline_config.py` | `config.py` | Load từ `configs/settings.yaml`; thiếu field → default; `DATABASE_URL` env override |

### 4.4. `src/ingestion/`

| File test | Đối tượng | Test cases chính |
|---|---|---|
| `test_data_cleaner.py` | `data_cleaner.py` | Normalize giá "10.990.000₫" → int; strip HTML; trim whitespace; duplicate records; missing fields |
| `test_spec_parser.py` | `spec_parser.py` | Parse "RAM 8 GB", "Pin 5000 mAh"; đơn vị lẫn lộn; spec string rác |
| `test_product_loader.py` / `test_review_loader.py` | loaders | Load JSON/CSV từ `tmp_path`; file không tồn tại; file rỗng; encoding UTF-8 tiếng Việt |
| `test_chunker.py` | (đã có) | Bổ sung: product thiếu field; field rất dài |
| `test_price_tracker.py` | `price_tracker.py` | Ghi nhận thay đổi giá; giá không đổi; lịch sử nhiều mốc |

### 4.5. `src/embedding/`

| File test | Đối tượng | Test cases chính |
|---|---|---|
| `test_product_embedder.py` | `product_embedder.py` | Chọn provider (OpenAI/Gemini) theo config; provider được gọi đúng input (mock); batch embedding |
| `test_multi_field_embedder.py` | `multi_field_embedder.py` | Embed nhiều field; field rỗng bị skip |
| `test_vector_store_sql.py` | `vector_store._build_where_sql` | **Logic thuần, unit-testable không cần DB**: where None; 1 điều kiện; nhiều điều kiện; giá trị đi vào params `%s` chứ không nội suy (guard chống SQL injection — khớp yêu cầu bandit) |

### 4.6. `src/crawler/` (đã tốt, chỉ bổ sung)

| File test | Đối tượng | Test cases chính |
|---|---|---|
| `test_http_client.py` | `http_client.py` | **Dùng `respx`**: retry khi 5xx; không retry 4xx; timeout; `aget`/`get_many` với semaphore (async — cần `pytest-asyncio`); tôn trọng robots disallow |
| `test_rate_limiter.py` | `rate_limiter.py` | Delay giữa 2 request (mock clock/monkeypatch `time`, không sleep thật); `await_ready` async |
| `test_storage.py` | `storage.py` | Ghi vào `tmp_path`; tên file; ghi đè/append |

### 4.7. `api/` + `src/utils/`

| File test | Đối tượng | Test cases chính |
|---|---|---|
| `test_schemas.py` | `api/schemas.py` | Pydantic validation: request thiếu field → 422 shape; giá trị biên (top_k=0, âm) |
| `test_deps.py` | `api/deps.py` | Factory trả đúng type; `get_cached_recommend_pipeline` trả cùng instance (cache); config override |
| `test_rate_limit_middleware.py` | `api/middleware/rate_limit.py` | Dưới limit pass; vượt limit → 429; reset window |
| `test_error_handler.py` | `api/middleware/error_handler.py` | Exception → JSON error đúng schema, message tiếng Việt, không leak stacktrace |
| `test_cache.py`, `test_helpers.py` | `src/utils/` | Cache hit/miss/expire; helpers theo hành vi cụ thể |

---

## 5. Giai đoạn 2 — Integration tests (`tests/integration/`)

Tất cả đánh dấu `@pytest.mark.integration`. Test cần DB tự skip khi thiếu `DATABASE_URL`:

```python
import os
import pytest

requires_pg = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set (Postgres integration tests run in CI)",
)
```

### 5.1. `tests/integration/conftest.py`

```python
"""Integration fixtures: real Postgres, TestClient with fake LLM/embedder."""
import pytest
from fastapi.testclient import TestClient

from api.app import app
from api import deps


@pytest.fixture
def client(fake_llm, fake_embedder, fake_vector_store):
    """TestClient with external services faked via dependency_overrides."""
    app.dependency_overrides[deps.get_llm_client] = lambda: make_llm_with(fake_llm)
    app.dependency_overrides[deps.get_embedder] = lambda: fake_embedder
    # keep real vector store only in pg-marked tests
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def pg_store():
    """Real VectorStore against DATABASE_URL, isolated collection per test."""
    store = VectorStore(collection_name=f"test_{uuid4().hex[:8]}")
    store.setup()
    yield store
    store.delete_collection()
    store.close()
```

### 5.2. Danh sách integration tests

| File | Kịch bản | External thật |
|---|---|---|
| `test_vector_store_pg.py` | `setup()` tạo extension/table; `add_documents` → `query` trả đúng thứ tự cosine; `where` filter (brand, price range); `delete_collection`; HNSW index tồn tại; concurrent add | Postgres ✅ |
| `test_api_recommend.py` | `POST /api/recommend` với query tiếng Việt → 200, response đúng `schemas`; body sai → 422; pipeline raise → error handler trả JSON chuẩn; rate limit → 429 | Không (fakes qua `dependency_overrides`) |
| `test_api_compare.py` | `POST /api/compare` 2 sản phẩm → 200 + bảng so sánh; sản phẩm không tồn tại → 4xx rõ ràng | Không |
| `test_api_search.py` | `POST /api/search` → kết quả + metadata; query rỗng → 422 | Không |
| `test_pipeline_e2e.py` | Ingest `sample_products` bằng `FakeEmbedder` vào **Postgres thật** → chạy `RecommendPipeline` với `FakeLLMProvider` → kiểm tra retrieval trả đúng sản phẩm và prompt gửi LLM chứa product context | Postgres ✅ |
| `test_crawler_pipeline.py` | `CrawlPipeline` với toàn bộ HTTP mock bằng `respx` (HTML fixture của TGDĐ/CellphoneS lưu trong `tests/fixtures/html/`) → ra `CrawledProduct` đúng và ghi vào `tmp_path` | Không |

### 5.3. Chạy tách unit / integration

```bash
uv run pytest tests/unit/                      # nhanh, không cần gì
uv run pytest tests/ -m integration            # cần DATABASE_URL
uv run pytest tests/                           # CI chạy toàn bộ (đã có pg service)
```

---

## 6. Giai đoạn 3 — Coverage & CI

1. Thêm cấu hình coverage vào `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src", "api"]
omit = ["src/utils/logger.py"]

[tool.coverage.report]
show_missing = true
```

2. **Mục tiêu coverage:** ≥ 80% cho `src/` và `api/` (đo bằng lệnh CI hiện tại `--cov=src --cov=api`). Sau khi đạt ổn định 2–3 tuần, thêm `--cov-fail-under=80` vào CI để gate.
3. CI đã có pg service + placeholder keys → **không cần sửa `ci.yml`** ngoài (tùy chọn) tách step `pytest -m "not integration"` chạy trước cho fail-fast.
4. `evaluation/` (eval_recommend, eval_compare) **không** đưa vào pytest suite — đó là offline quality eval cần LLM thật, giữ chạy thủ công.

---

## 7. Thứ tự triển khai & ước lượng

| Bước | Nội dung | Ước lượng | Phụ thuộc |
|---|---|---|---|
| 1 | Giai đoạn 0: deps, pytest config, dọn cấu trúc tests, fakes trong conftest | 0.5–1 ngày | — |
| 2 | Unit: `generation/` + `retrieval/` | 1.5–2 ngày | Bước 1 |
| 3 | Unit: `pipeline/` (router, recommend/, compare/, 2 pipelines) | 2 ngày | Bước 2 (dùng fakes) |
| 4 | Unit: `ingestion/` + `embedding/` | 1–1.5 ngày | Bước 1 |
| 5 | Unit: `crawler/` bổ sung + `api/` + `utils/` | 1–1.5 ngày | Bước 1 |
| 6 | Integration: vector store pg + API routes + e2e + crawler pipeline | 2–3 ngày | Bước 3, 4 |
| 7 | Coverage tuning, gate, tài liệu `docs/` (EN + `.vi.md`) nếu cần | 0.5 ngày | Bước 6 |

**Tổng: ~8–11 ngày công**, có thể song song bước 2–5 nếu nhiều người làm.

---

## 8. Definition of Done (mỗi PR test)

- [ ] `uv run pytest tests/` xanh trên local (unit) — integration xanh trên CI.
- [ ] Không gọi network/API thật, không cần secret thật (khớp `gitleaks.yml`).
- [ ] `uvx ruff check .` và `uvx ruff format .` sạch (không F401/F841).
- [ ] Type hints đầy đủ trên fixture/helper signatures (mypy advisory).
- [ ] `uvx bandit -r src api scripts -ll -ii -s B608` không MEDIUM+.
- [ ] Nếu thêm dep: qua `uv add --group dev`, `uv.lock` cập nhật, `uvx pip-audit` sạch.
- [ ] Test mới nằm đúng thư mục (`unit/<module>/` hoặc `integration/`), có marker phù hợp.
