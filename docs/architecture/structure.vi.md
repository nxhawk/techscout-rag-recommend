# Cấu trúc dự án

## Cây thư mục

```
rag-product-recommend/
├── pyproject.toml              # Dependencies & metadata dự án
├── uv.lock                     # Lockfile (tương tự package-lock.json)
├── .env                        # API keys (không commit)
├── CLAUDE.md                   # Ngữ cảnh AI & quy tắc coding
│
├── src/                        # Logic nghiệp vụ cốt lõi
│   ├── crawler/                # Web crawling (thu thập dữ liệu thô)
│   │   └── spiders/            #   Một spider cho mỗi nguồn (tgdd, cellphones)
│   ├── catalog/                # Bảng sản phẩm source-of-truth (CRUD)
│   ├── ingestion/               # Nạp & chuẩn hóa dữ liệu
│   ├── embedding/               # Embedding & Vector DB
│   ├── retrieval/               # Truy xuất & tìm kiếm sản phẩm
│   ├── sync/                   # CDC sync worker (Debezium → ES/pgvector)
│   ├── generation/               # Sinh nội dung bằng LLM & prompt
│   ├── guardrails/              # Validate input/context/output không dùng LLM
│   │   ├── input/               #   normalize, heuristics, denylist injection
│   │   ├── context/              #   sanitize dữ liệu sản phẩm đã truy xuất
│   │   └── output/               #   validate schema + grounding
│   ├── pipeline/                # Tầng điều phối
│   │   ├── recommend/          #   Logic nghiệp vụ gợi ý
│   │   └── compare/            #   Logic nghiệp vụ so sánh
│   └── utils/                  # Tiện ích dùng chung
│
├── api/                        # Tầng FastAPI
│   ├── routes/                 #   Route handler của API
│   └── middleware/             #   Middleware request/response
│
├── tests/                      # Bộ test
│   ├── unit/                   #   Unit test
│   └── integration/            #   Integration test
│
├── evaluation/                 # Đánh giá chất lượng RAG
├── scripts/                    # Script CLI
├── configs/                    # File cấu hình YAML
├── docs/                       # Mã nguồn tài liệu MkDocs
├── docker/                     # File Docker & Compose
└── data/                       # Thư mục dữ liệu (một phần gitignored)
```

---

## File gốc

| File | Mục đích | Khi nào cập nhật |
| ---- | ------- | -------------- |
| `pyproject.toml` | Metadata dự án, dependencies, cấu hình build | Khi thêm/xóa dependency (`uv add`), đổi version Python, hoặc cập nhật metadata dự án |
| `uv.lock` | Ghim chính xác version dependency (tự sinh) | Không bao giờ sửa tay — được sinh lại bởi `uv lock` hoặc `uv add` |
| `.env` | Biến môi trường (API key, log level) | Khi thêm provider mới hoặc đổi cấu hình môi trường. **Không commit vào git.** |
| `.env.example` | Template cho `.env` | Khi cần một biến môi trường mới — thêm vào đây để các dev khác biết |
| `CLAUDE.md` | Quy tắc coding cho AI + tham chiếu cấu trúc dự án | Khi cấu trúc dự án thay đổi, có convention mới, hoặc cần cập nhật quy tắc ngôn ngữ |
| `mkdocs.yml` | Cấu hình site MkDocs Material | Khi thêm trang docs mới, đổi navigation, hoặc cập nhật theme/plugin |
| `.gitignore` | Quy tắc bỏ qua của Git | Khi cần loại trừ file mới được sinh ra/chứa thông tin nhạy cảm |

---

## `src/` — Logic nghiệp vụ cốt lõi

Toàn bộ logic domain nằm ở đây. Đây là một Python package thuần túy, không phụ thuộc vào web framework — có thể dùng độc lập với FastAPI.

### `src/crawler/` — Web Crawling

**Mục đích:** Thu thập dữ liệu sản phẩm thô (thông số + đánh giá người mua) từ các trang thương mại điện tử vào `data/raw/crawled/`. Stack nhẹ: `httpx` + `BeautifulSoup`. Xem [hướng dẫn Crawler](../development/crawler.md) để biết toàn bộ luồng.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `config.py` | `CrawlerConfig` / `SourceConfig` — nạp từ `configs/crawler.yaml` (nguồn, mức độ lịch sự, `fetch_reviews`, `max_products`) | Khi thêm một cấu hình mới hoặc một block nguồn mới |
| `http_client.py` | Wrapper `httpx` với retry (tenacity), rate limiting, và kiểm tra robots.txt; fetch đồng bộ + async đồng thời | Khi đổi hành vi HTTP (header, chính sách retry, concurrency) |
| `rate_limiter.py` | Độ trễ tối thiểu giữa các request đến cùng một host (sync + async) | Khi đổi chiến lược "lịch sự" (politeness) |
| `robots.py` | Lấy và cache rule `robots.txt` theo từng host | Khi đổi cách xử lý robots |
| `parser.py` | Helper BeautifulSoup dùng chung: giá/rating, nhóm thông số (`parse_spec_groups`, `canonical_spec_group`), trích xuất đánh giá bền vững (`star_rating`, `review_content`), helper JSON cho review | Khi thêm một helper parsing dùng chung |
| `models.py` | Dataclass `CrawledProduct` (gồm `specifications`, `spec_groups`, `reviews`), `Review`, `CrawlResult` | Khi thêm một trường vào schema output của crawl |
| `storage.py` | Ghi kết quả vào `data/raw/crawled/<source>/` (`<timestamp>.json` + `latest.json`) | Khi đổi cấu trúc output |
| `pipeline.py` | `CrawlPipeline` điều phối một spider từ đầu đến cuối: discover → fetch → parse → store | Khi đổi cách điều phối crawl |

**`src/crawler/spiders/`** — Một spider cho mỗi nguồn. Kế thừa `BaseSpider` và implement `build_list_url`, `parse_list`, `parse_detail`; có thể override thêm các hook review (`parse_reviews`, `parse_reviews_payload`) và đăng ký trong `SPIDER_REGISTRY`.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `base_spider.py` | Spider trừu tượng: phân trang (`discover`), fetch chi tiết đồng thời, thu thập thông số theo nhóm + review, ghi nhận lỗi | Khi đổi hành vi spider dùng chung |
| `tgdd_spider.py` | Spider cho thegioididong.com | Khi markup của TGDĐ thay đổi |
| `cellphones_spider.py` | Spider cho cellphones.com.vn | Khi markup của CellphoneS thay đổi |

**Khi nào thêm file mới:** Khi crawl một nguồn mới — thêm `<name>_spider.py` và một block `SourceConfig` trong `configs/crawler.yaml`.

### `src/catalog/` — Source of Truth (Catalog sản phẩm)

**Mục đích:** Truy cập CRUD vào bảng `product_catalog` — source of truth duy nhất mà CDC capture. Các index tìm kiếm được dẫn xuất từ nó và không bao giờ được API handler ghi trực tiếp.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | -------- | ---------------------- |
| `product_repository.py` | `ProductRepository` — create/upsert/update/delete/get/list trên `product_catalog` (SQL parameterized, `REPLICA IDENTITY FULL` cho before-image Debezium) | Khi thêm trường sản phẩm (nhớ cập nhật cả `api/schemas.py` và chunker) |

### `src/ingestion/` — Nạp & chuẩn hóa dữ liệu

**Mục đích:** Nạp dữ liệu sản phẩm thô từ nhiều nguồn khác nhau, làm sạch, parse thông số, và chia nhỏ thành các đơn vị phù hợp để embedding.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `product_loader.py` | Nạp dữ liệu sản phẩm từ file JSON/CSV | Khi hỗ trợ một định dạng nguồn dữ liệu mới (vd: XML, export database) |
| `review_loader.py` | Nạp đánh giá và rating của người dùng | Khi thêm nguồn đánh giá mới hoặc đổi schema review |
| `data_cleaner.py` | Chuẩn hóa text, sửa encoding, loại trùng | Khi thêm quy tắc làm sạch mới (vd: chuẩn hóa tiền tệ, loại bỏ HTML) |
| `spec_parser.py` | Parse thông số sản phẩm thành cặp key-value có cấu trúc | Khi hỗ trợ một danh mục sản phẩm mới với định dạng thông số khác |
| `chunker.py` | Chia nhỏ theo trường — tách dữ liệu sản phẩm thành các chunk có thể embedding | Khi đổi chiến lược chunking (vd: kích thước chunk, overlap, gom nhóm trường) |
| `price_tracker.py` | Theo dõi lịch sử giá và phát hiện thay đổi giá | Khi thêm logic cảnh báo giá hoặc nguồn dữ liệu giá mới |

**Khi nào thêm file mới:** Khi cần một loại nguồn dữ liệu mới (vd: `api_loader.py` cho REST API) hoặc một bước tiền xử lý mới (vd: `deduplicator.py`).

### `src/embedding/` — Embedding & Vector DB

**Mục đích:** Chuyển văn bản thành vector và quản lý vector database (Postgres + pgvector).

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `product_embedder.py` | Embed văn bản thành vector bằng `text-embedding-3-small` của OpenAI | Khi đổi embedding model hoặc thêm provider embedding mới |
| `multi_field_embedder.py` | Sinh embedding riêng cho từng trường sản phẩm (tên, mô tả, thông số) | Khi đổi trường nào có embedding riêng hoặc điều chỉnh trọng số trường |
| `vector_store.py` | Thao tác CRUD cho Postgres + pgvector — tạo bảng/chỉ mục, upsert, query, xóa | Khi đổi vector DB provider, thêm pattern query mới, hoặc đổi metric similarity |

**Khi nào thêm file mới:** Khi thêm một chiến lược embedding mới (vd: `sparse_embedder.py` cho vector BM25) hoặc một backend vector DB mới.

### `src/retrieval/` — Truy xuất & tìm kiếm sản phẩm

**Mục đích:** Với một truy vấn người dùng, truy xuất các sản phẩm liên quan nhất từ vector store bằng cách kết hợp semantic search, khớp từ khóa, và lọc metadata.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `product_retriever.py` | Retriever chính — kết hợp trích xuất filter, embedding, truy vấn vector, và chấm điểm thành một luồng | Khi đổi thứ tự pipeline truy xuất hoặc thêm bước truy xuất mới |
| `hybrid_search.py` | Hợp nhất nhánh semantic + keyword bằng RRF; hỗ trợ backend pre-filter (ES) và fallback BM25 in-memory post-filter | Khi thêm chiến lược tìm kiếm mới hoặc đổi hành vi fusion |
| `es_keyword_search.py` | Backend keyword Elasticsearch — BM25 với pre-filter `bool.filter`, upsert/delete chunk cho sync worker | Khi đổi mapping ES, dạng query, hoặc filter pushdown |
| `filter_engine.py` | Trích xuất filter có cấu trúc (giá, thương hiệu, danh mục, rating) từ truy vấn ngôn ngữ tự nhiên tiếng Việt | Khi hỗ trợ loại filter mới (vd: màu sắc, dung lượng) hoặc thêm pattern từ khóa mới |
| `similarity_scorer.py` | Tính composite relevance score từ độ tương đồng ngữ nghĩa + tín hiệu metadata | Khi đổi trọng số chấm điểm hoặc thêm chiều chấm điểm mới |
| `reranker.py` | Rerank bằng cross-encoder `ms-marco-MiniLM-L-6-v2` để chấm điểm liên quan chính xác hơn | Khi đổi model reranker hoặc thêm chiến lược rerank (vd: rerank bằng LLM) |

**Khi nào thêm file mới:** Khi thêm một chiến lược tìm kiếm mới (vd: `bm25_search.py`), một loại filter đủ phức tạp để cần module riêng, hoặc một thuật toán chấm điểm mới.

### `src/sync/` — CDC Sync Worker

**Mục đích:** Consume stream thay đổi Debezium (Kafka) và giữ các index tìm kiếm dẫn xuất đồng bộ với catalog. Xem [Truy xuất lai](hybrid-retrieval.vi.md).

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | -------- | ---------------------- |
| `events.py` | Parse message Debezium thành `ChangeEvent`; `TEXT_FIELDS` / `content_hash` / `text_changed` quyết định khi nào cần re-embed | Khi thêm trường sản phẩm (quyết định: mang text hay chỉ metadata) |
| `chunk_builder.py` | Row catalog → chunk payload (ids, documents, metadatas kèm `content_hash`), dùng chung với ingest | Khi đổi cấu trúc chunk |
| `indexer_worker.py` | `SearchIndexer` — upsert/delete chunk idempotent vào Elasticsearch | Khi đổi hành vi index keyword |
| `embedding_worker.py` | `EmbeddingSyncer` — re-embed khi text đổi, update metadata-only cho giá/rating, xóa khi `d` | Khi đổi logic quyết định re-embed hoặc luồng upsert vector |
| `runner.py` | Vòng lặp Kafka consumer — at-least-once, commit sau khi áp xong | Khi đổi ngữ nghĩa delivery hoặc xử lý lỗi |

### `src/generation/` — Sinh nội dung bằng LLM

**Mục đích:** Gọi LLM provider, quản lý prompt template, parse phản hồi, và validate input/output.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `llm_client.py` | Client thống nhất cho Anthropic, OpenAI, và Gemini — mọi lời gọi LLM đều đi qua đây | Khi thêm LLM provider mới hoặc đổi interface của client |
| `response_parser.py` | Parse JSON có cấu trúc từ output văn bản của LLM | Khi đổi định dạng phản hồi mong đợi hoặc thêm loại phản hồi mới |
| `guardrails.py` | **Legacy** — module input/output cũ, đã được thay thế bởi `src/guardrails/` (bên dưới); không còn pipeline nào gọi tới | Không mở rộng module này; thêm kiểm tra mới vào `src/guardrails/` |

**`src/generation/prompt_templates/`** — Một file cho mỗi use case, mỗi file export `SYSTEM_PROMPT` và `USER_PROMPT_TEMPLATE` dưới dạng hằng số ở cấp module.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `recommend_prompt.py` | Prompt cho phản hồi gợi ý sản phẩm | Khi tinh chỉnh chất lượng output gợi ý hoặc đổi định dạng phản hồi |
| `compare_prompt.py` | Prompt cho phản hồi so sánh sản phẩm | Khi điều chỉnh tiêu chí so sánh hoặc cấu trúc output |
| `review_summary_prompt.py` | Prompt để tóm tắt đánh giá người dùng | Khi thêm tính năng tóm tắt review |

**Khi nào thêm file mới:** Khi tạo một loại pipeline mới (vd: `faq_prompt.py` cho pipeline FAQ) hoặc một LLM provider mới cần module client riêng.

### `src/guardrails/` — Guardrail không dùng LLM

**Mục đích:** Validate rule/heuristic/schema cho cả hai pipeline — không gọi LLM. Mọi guardrail đều trả về cùng một `GuardrailResult` (`allow` / `sanitize` / `block`). Xem [Guardrail](guardrails.vi.md) để biết đầy đủ contract và sơ đồ.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `types.py` | `GuardrailAction`, `GuardrailResult` — contract kết quả dùng chung | Khi shape kết quả cần thêm trường mới |
| `base.py` | `BaseGuardrail` (ABC), `GuardrailChain` (chạy danh sách guardrail, short-circuit khi `block`) | Khi đổi cách các guardrail được ghép nối |
| `config.py` | `GuardrailConfig` — mọi ngưỡng (độ dài query, số URL, độ dài field context, `max_compare_products`, ...) tập trung một chỗ | Khi thêm một giới hạn có thể chỉnh mới |
| `exceptions.py` | `InputGuardrailBlocked` — pipeline raise, route map thành `HTTP 422` | Khi đổi contract block/error |
| `logging_utils.py` | `log_guardrail_event()` — log có cấu trúc `guardrail=... action=... reason=...` | Khi đổi định dạng log |
| `fallback.py` | `build_recommend_fallback()` / `build_compare_fallback()` — phản hồi tất định dựng từ dữ liệu đã truy xuất, không gọi lại LLM | Khi đổi hình dạng phản hồi degraded |

**`src/guardrails/input/`** — Kiểm tra truy vấn thô, theo thứ tự, trước khi truy xuất.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `normalize.py` | `NormalizeGuardrail` — Unicode NFC, bỏ ký tự điều khiển, gộp khoảng trắng (luôn `sanitize`) | Khi đổi quy tắc chuẩn hóa text |
| `heuristics.py` | `HeuristicGuardrail` — kiểm tra rỗng/độ dài/số URL/code block/ký tự lặp | Khi tinh chỉnh ngưỡng độ dài hoặc heuristic |
| `injection.py` | `InjectionGuardrail` — regex denylist cho prompt injection/jailbreak (tiếng Anh + tiếng Việt) | Khi thêm cách diễn đạt injection mới cần chặn |

**`src/guardrails/context/`** — Sanitize dữ liệu sản phẩm đã truy xuất trước khi đưa vào prompt.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `sanitizer.py` | `sanitize_text_field()` / `sanitize_product_fields()` — bỏ HTML/script + câu chứa chỉ dẫn giả mạo, cắt độ dài | Khi có trường sản phẩm dạng text tự do mới cần sanitize |

**`src/guardrails/output/`** — Validate và grounding phản hồi JSON của LLM.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `schemas.py` | `RecommendLLMOutput`, `CompareLLMOutput` — model Pydantic khớp đúng contract JSON của từng prompt template | Khi contract JSON của prompt template thay đổi |
| `validator.py` | Parse JSON (qua `ResponseParser`) và validate theo schema tương ứng | Khi đổi cách xử lý lỗi parse |
| `grounding.py` | `ground_recommendations()` / `ground_compare_analysis()` — loại item có tên không khớp sản phẩm đã truy xuất/so sánh | Khi đổi quy tắc so khớp tên |

**Khi nào thêm file mới:** Khi thêm guardrail cho một pipeline mới (vd `/api/search`) — tái sử dụng `build_input_chain()` và `sanitize_text_field()` thay vì viết lại logic.

### `src/pipeline/` — Tầng điều phối

**Mục đích:** Kết nối retrieval, scoring, và generation thành các pipeline end-to-end. Đây là tầng "keo dán".

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `rag_router.py` | Phân loại truy vấn đến (RECOMMEND / COMPARE / INFO / HYBRID) bằng regex pattern | Khi thêm loại truy vấn mới hoặc cải thiện độ chính xác phân loại |
| `config.py` | Dataclass `PipelineConfig` — nạp từ `configs/settings.yaml` | Khi thêm tham số cấu hình mới (vd: provider mới, ngưỡng mới) |
| `recommend_pipeline.py` | Luồng gợi ý end-to-end: intent → retrieve → score → LLM → response | Khi đổi các bước pipeline gợi ý hoặc thêm bước pre/post-processing |
| `compare_pipeline.py` | Luồng so sánh end-to-end: lấy sản phẩm → so sánh → LLM → response | Khi đổi các bước pipeline so sánh |

**`src/pipeline/recommend/`** — Logic nghiệp vụ gợi ý (được gọi bởi `recommend_pipeline.py`).

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `engine.py` | Engine gợi ý chính — điều phối parse intent, retrieval, và scoring | Khi đổi thuật toán gợi ý |
| `user_intent_parser.py` | Parse truy vấn tiếng Việt thành ý định có cấu trúc (budget, use_case, priorities, brand) | Khi hỗ trợ trường intent mới hoặc cải thiện độ chính xác NLP |
| `scoring.py` | Chấm điểm sản phẩm đa tiêu chí (độ khớp giá, rating, độ khớp tính năng) | Khi thêm tiêu chí chấm điểm mới hoặc điều chỉnh trọng số |
| `personalization.py` | Tăng điểm dựa trên lịch sử và sở thích người dùng | Khi thêm tính năng cá nhân hóa (vd: collaborative filtering) |

**`src/pipeline/compare/`** — Logic nghiệp vụ so sánh (được gọi bởi `compare_pipeline.py`).

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `comparator.py` | So sánh N sản phẩm trên mọi chiều thông số kỹ thuật | Khi đổi logic so sánh hoặc hỗ trợ loại sản phẩm mới |
| `spec_aligner.py` | Chuẩn hóa và đối chiếu thông số giữa các sản phẩm về một schema chung | Khi xử lý định dạng thông số mới hoặc cải thiện độ chính xác đối chiếu |
| `formatter.py` | Định dạng kết quả so sánh thành bảng Markdown | Khi đổi định dạng output (vd: HTML, JSON có cấu trúc) |
| `pros_cons_extractor.py` | Trích xuất ưu điểm và nhược điểm của từng sản phẩm | Khi cải thiện logic trích xuất ưu/nhược điểm |

**Khi nào thêm file mới trong `src/pipeline/`:** Khi tạo hẳn một pipeline mới (vd: `faq_pipeline.py` + thư mục con `faq/` cho pipeline trả lời FAQ).

### `src/utils/` — Tiện ích dùng chung

**Mục đích:** Helper dùng chung cho nhiều module.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `logger.py` | Thiết lập logging có cấu trúc | Khi đổi định dạng log hoặc thêm đích ghi log |
| `cache.py` | Tầng cache (dùng Redis) cho embedding và phản hồi LLM | Khi thêm chiến lược cache mới hoặc đổi TTL |
| `helpers.py` | Hàm tiện ích dùng chung | Khi thêm một helper nhỏ không thuộc module cụ thể nào |

**Khi nào thêm file mới:** Khi một tiện ích phát triển vượt quá vài hàm và xứng đáng có module riêng (vd: `metrics.py` để theo dõi hiệu năng).

---

## `api/` — Tầng FastAPI

**Mục đích:** Giao diện HTTP cho pipeline. Tầng mỏng — route validate input, gọi pipeline factory từ `deps.py`, và trả về JSON.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `app.py` | Điểm khởi tạo ứng dụng FastAPI — mount route, middleware, CORS, health check | Khi thêm nhóm route mới hoặc middleware mới |
| `schemas.py` | Model Pydantic cho request/response | Khi đổi API contract (trường mới, endpoint mới) |
| `deps.py` | Factory function cho dependency injection (`get_retriever()`, `get_llm_client()`, ...) | Khi thêm component pipeline mới hoặc đổi cách kết nối các component |

**`api/routes/`** — Một file cho mỗi domain API.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `recommend.py` | Handler cho `POST /api/recommend` | Khi đổi định dạng request/response gợi ý |
| `compare.py` | Handler cho `POST /api/compare` | Khi đổi định dạng request/response so sánh |
| `search.py` | Handler cho `POST /api/search` | Khi thêm tính năng hoặc filter tìm kiếm |
| `products.py` | `POST/PUT/DELETE/GET /api/products` — CRUD trên catalog source-of-truth (CDC lan truyền sang các index) | Khi đổi contract ghi sản phẩm |

**`api/middleware/`** — Middleware request/response.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `rate_limit.py` | Rate limit theo IP/API key | Khi điều chỉnh giới hạn rate hoặc thêm giới hạn theo user |
| `error_handler.py` | Xử lý exception toàn cục — chuyển exception thành JSON error response nhất quán | Khi thêm loại exception mới hoặc đổi định dạng lỗi |

**Khi nào thêm file mới:** Khi tạo một domain API mới (vd: `routes/admin.py`) hoặc một middleware mới (vd: `middleware/auth.py` cho xác thực).

---

## `tests/` — Bộ test

**Mục đích:** Test tự động dùng pytest. Unit test phản chiếu layout của `src/` và `api/`.

| Path | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `conftest.py` | Fixture dùng chéo domain (`sample_product`, `sample_products`) | Khi thêm fixture cần bởi nhiều domain |
| `unit/<domain>/` | Unit test cho một domain (`api/`, `retrieval/`, `pipeline/`, …) | Thêm folder khi có domain mới ở `src/` hoặc `api/` |
| `unit/<domain>/conftest.py` | Fixture dùng chung trong một domain (vd. API `TestClient`) | Khi nhiều file test cùng domain chia sẻ setup |
| `integration/` | Integration test — luồng đầy đủ với dependency thật (hoặc docker) | Thêm test khi pipeline/endpoint cần coverage có dịch vụ |

**Layout (unit):**

```
tests/unit/
├── api/              # schemas, metrics, routes/
├── embedding/
├── guardrails/
├── ingestion/
├── pipeline/
├── retrieval/
├── sync/
└── utils/
```

**Quy ước đặt tên:** `tests/unit/<domain>/test_<module>.py` tương ứng với
`src/<domain>/<module>.py` hoặc `api/<path>/<module>.py`. Test route đặt trong
`tests/unit/api/routes/test_<route>.py`.

---

## `evaluation/` — Đánh giá chất lượng RAG

**Mục đích:** Đo lường chất lượng retrieval và generation dựa trên pipeline thật (embedder + vector store + LLM). Chạy thủ công để benchmark các thay đổi — các script này chủ đích không nằm trong bộ pytest (xem `TEST_PLAN.md`), vì cần LLM/DB thật thay vì mock.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `eval_recommend.py` | `RecommendEvaluator` chạy từng case `type: "recommend"` qua `RecommendPipeline` thật và chấm 4 metric — `relevance`, `budget_fit`, `intent_recall`, `faithfulness` (xem chi tiết ở [Đánh giá](../development/testing.vi.md#danh-gia-evaluation)) | Khi đổi logic retrieval, scoring, hoặc prompt gợi ý — chạy trước/sau để so sánh |
| `eval_compare.py` | Đánh giá pipeline so sánh (độ chính xác đối chiếu thông số, chất lượng phân tích) — hiện vẫn là TODO stub, chưa nối với `ComparePipeline` | Khi implement/đổi logic so sánh |
| `test_case/test_cases_recommend.json` | Test case ground-truth cho recommend với kết quả kỳ vọng (`expected_category`, `expected_price_range`, `expected_features`) | Khi thêm danh mục sản phẩm mới hoặc edge case mới |
| `test_case/test_cases_compare.json` | Test case ground-truth cho compare với kết quả kỳ vọng (`expected_products`, `expected_criteria`) | Khi thêm kịch bản so sánh mới |

**Khi nào thêm file mới:** Khi tạo một metric đánh giá mới (vd: `eval_latency.py`) hoặc một pipeline mới cần đánh giá.

---

## `scripts/` — Script CLI

**Mục đích:** Tác vụ chạy một lần hoặc định kỳ, thực thi từ command line.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `crawl.py` | Crawl dữ liệu sản phẩm thô vào `data/raw/crawled/` (`--source`, `--category`, `--all`) | Khi đổi option CLI của crawl hoặc thêm nguồn mới |
| `ingest.py` | Pipeline nạp dữ liệu đầy đủ: load → clean → chunk → embed → lưu vào Postgres (pgvector) | Khi đổi luồng ingestion hoặc thêm nguồn dữ liệu mới |
| `seed.py` | Sinh dữ liệu sản phẩm mẫu cho phát triển/testing | Khi thêm danh mục sản phẩm mới hoặc đổi schema dữ liệu mẫu |
| `sync_worker.py` | Chạy CDC sync worker (`--role indexer` → Elasticsearch, `--role embedder` → pgvector) | Khi thêm index dẫn xuất mới hoặc đổi wiring worker |

**Khi nào thêm file mới:** Khi cần một tác vụ CLI mới (vd: `migrate.py` cho migration vector store, `export.py` cho export dữ liệu).

---

## `configs/` — File cấu hình

**Mục đích:** File cấu hình YAML. Được nạp khi khởi động, không phải secret được commit.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `settings.yaml` | Cấu hình pipeline chính — LLM provider, embedding model, vector DB, tham số retrieval | Khi đổi bất kỳ tham số pipeline nào |
| `crawler.yaml` | Nguồn crawler, mức độ lịch sự, cài đặt review + số lượng (`fetch_reviews`, `max_products`, `max_pages`) | Khi thêm nguồn hoặc tinh chỉnh hành vi crawl |
| `product_categories.yaml` | Định nghĩa danh mục sản phẩm với các trường bắt buộc theo từng danh mục | Khi hỗ trợ danh mục sản phẩm mới (vd: camera, màn hình) |
| `scoring_weights.yaml` | Trọng số chấm điểm theo use case (vd: gaming ưu tiên hiệu năng, photography ưu tiên camera) | Khi tinh chỉnh chất lượng gợi ý cho use case cụ thể |

**Khi nào thêm file mới:** Khi một component mới cần cấu hình riêng (vd: `rate_limits.yaml`, `reranker.yaml`).

---

## `docs/` — Mã nguồn tài liệu

**Mục đích:** File nguồn MkDocs Material. Được build thành static site và deploy lên GitHub Pages.

| Path | Nội dung | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `index.md` | Trang chủ | Khi tổng quan dự án thay đổi |
| `getting-started/` | Cài đặt, quickstart, hướng dẫn phát triển | Khi các bước setup thay đổi |
| `architecture/` | Tổng quan hệ thống, luồng pipeline, cấu trúc dự án | Khi kiến trúc thay đổi |
| `api/` | Endpoint API và tham chiếu schema | Khi API contract thay đổi |
| `development/` | Hướng dẫn đóng góp, hướng dẫn crawler, hướng dẫn testing | Khi quy trình phát triển thay đổi |

**Khi nào thêm file mới:** Khi tài liệu hóa một tính năng lớn mới hoặc thêm một section mới (vd: `deployment/` cho hướng dẫn triển khai production). Nhớ thêm trang vào `nav` trong `mkdocs.yml`.

---

## `docker/` — Cấu hình Container

**Mục đích:** File Docker và Compose cho triển khai containerized.

| File | Mục đích | Khi nào thêm/cập nhật |
| ---- | ------- | ------------------- |
| `Dockerfile` | Multi-stage build dùng uv — cài dependency, copy source, chạy uvicorn | Khi đổi base image, version Python, hoặc bước build |
| `docker-compose.yml` | Stack CDC đầy đủ: app, Postgres (wal_level=logical), Elasticsearch, Kafka (KRaft), Debezium Connect + connect-init, hai sync worker, Redis | Khi thêm service mới hoặc đổi port/volume |
| `debezium/product-catalog-connector.json` | Cấu hình Debezium Postgres connector (đăng ký idempotent bởi `connect-init`) | Khi đổi bảng capture, topic prefix, hoặc snapshot mode |

---

## `data/` — Thư mục dữ liệu

**Mục đích:** Dữ liệu thô, đã xử lý, và vector. Một phần được gitignore.

| Path | Nội dung | Trạng thái Git | Khi nào cập nhật |
| ---- | ------- | ---------- | -------------- |
| `raw/products/` | Dữ liệu sản phẩm gốc (JSON, CSV) | Tracked | Khi thêm file dữ liệu sản phẩm mới |
| `raw/crawled/` | Output crawler thô theo từng nguồn (`<timestamp>.json` + `latest.json`) | Gitignored | Tự động sinh bởi `scripts/crawl.py` |
| `processed/` | Dữ liệu đã làm sạch và chuẩn hóa (output của `data_cleaner.py`) | Gitignored | Tự động sinh bởi pipeline ingestion |
| `embeddings/` | Thư mục persist cũ của ChromaDB (không còn dùng — vector giờ nằm trong Postgres) | Gitignored | Có thể xóa an toàn |

---

## Quy ước chính

| Quy ước | Quy tắc |
| ---------- | ---- |
| Import | Luôn dùng đường dẫn tuyệt đối từ root dự án: `from src.retrieval.filter_engine import FilterEngine` |
| Config | Dataclass `PipelineConfig` nạp từ `configs/settings.yaml` |
| Lời gọi LLM | Luôn đi qua `src/generation/llm_client.py` — không bao giờ gọi trực tiếp API provider |
| Vector DB | Luôn đi qua `src/embedding/vector_store.py` |
| Prompt template | Hằng số cấp module: `SYSTEM_PROMPT`, `USER_PROMPT_TEMPLATE` |
| API dependency | Factory function trong `api/deps.py` (vd: `get_retriever()`, `get_llm_client()`) |
| Guardrail | Kiểm tra input/context/output không dùng LLM luôn đi qua `src/guardrails/` (xem [Guardrail](guardrails.vi.md)) — không bao giờ dùng `src/generation/guardrails.py` (legacy) |
| Văn bản hiển thị cho người dùng | Tiếng Việt |
| Code & comment | Tiếng Anh |
| Quản lý package | Chỉ dùng `uv` — không bao giờ `pip install` |
| Module mới | Luôn thêm file test tương ứng trong `tests/unit/<domain>/` (mirror đường dẫn module) |
