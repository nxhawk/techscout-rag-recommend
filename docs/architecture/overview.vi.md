# Tổng quan kiến trúc

Hệ thống tuân theo kiến trúc RAG tiêu chuẩn với năm tầng cốt lõi:

## Luồng End-to-End

Sơ đồ dưới đây bao quát toàn bộ hệ thống: luồng nạp dữ liệu **offline** đổ vào vector store, và luồng **online** xử lý một truy vấn của người dùng.

```mermaid
flowchart TD
    subgraph Offline["Nạp dữ liệu (offline, theo batch)"]
        direction TB
        SRC["Trang thương mại điện tử\n(TGDD, CellphoneS)"] --> CRAWL[Crawler]
        CRAWL --> RAW[("data/raw/crawled/")]
        RAW --> CLEAN[DataCleaner]
        CLEAN --> SPEC[SpecParser]
        SPEC --> CHUNK["Chunker\n(chia theo từng trường)"]
        CHUNK --> EMBED[ProductEmbedder]
        EMBED --> VDB[("Postgres + pgvector\nvector + metadata")]
        CLEAN -->|"upsert profile\n(bootstrap)"| CAT
    end

    subgraph Sync["Catalog & CDC Sync (liên tục)"]
        direction TB
        CRUD["API CRUD sản phẩm\nPOST/PUT/DELETE /api/products"] --> CAT[("product_catalog\nsource of truth")]
        CAT -->|"WAL → Debezium"| KAFKA["Kafka topic"]
        KAFKA --> IW["Indexer worker"]
        IW --> ESI[("Elasticsearch\nBM25 keyword index")]
        KAFKA --> EW["Embedding worker\n(chỉ re-embed khi\ntext thay đổi)"]
        EW --> VDB
    end

    subgraph Online["Xử lý truy vấn (online, theo từng request)"]
        direction TB
        Q[Truy vấn người dùng] --> GIN["Guardrail đầu vào\n(normalize + heuristics + injection)"]
        GIN -->|block| E422["HTTP 422\n(lý do bằng tiếng Việt)"]
        GIN -->|allow / sanitize| ROUTER{RAG Router}

        ROUTER -->|RECOMMEND| RI[UserIntentParser]
        RI --> RF[FilterEngine]
        RF --> RR[ProductRetriever]
        RR --> RRK[CrossEncoderReranker]
        RRK --> RSC[ProductScorer]

        ROUTER -->|COMPARE| CX[Trích xuất sản phẩm]
        CX --> CR[ProductRetriever]
        CR --> CAL[SpecAligner]
        CAL --> CFM[ComparisonFormatter]

        RSC --> GCTX["Guardrail ngữ cảnh\n(sanitize dữ liệu sản phẩm)"]
        CFM --> GCTX
        GCTX --> LLM["LLM Client\n(Anthropic / OpenAI / Gemini)"]
        LLM --> RP[ResponseParser]
        RP --> GOUT["Guardrail đầu ra\n(validate schema + grounding)"]
        GOUT -->|không hợp lệ / ungrounded| FB["Fallback tất định\n(không gọi lại LLM)"]
        GOUT -->|hợp lệ & grounded| RESP["JSON Response\n+ warnings[]"]
        FB --> RESP
    end

    VDB -.->|"tìm kiếm vector + metadata"| RR
    VDB -.->|"tìm kiếm vector + metadata"| CR
    ESI -.->|"BM25 keyword search\n(pre-filter)"| RR
```

## Sequence Diagram End-to-End

Sơ đồ tuần tự dưới đây thể hiện cùng luồng online nhưng theo dạng timeline của một request, bao gồm cả nhánh rẽ `RECOMMEND` và `COMPARE`.

```mermaid
sequenceDiagram
    actor User as Người dùng
    participant API as FastAPI Route
    participant Pipe as Recommend/Compare Pipeline
    participant Guard as Guardrails (src/guardrails/)
    participant VDB as Postgres (pgvector)
    participant LLM as LLM Client

    User->>API: POST /api/recommend hoặc /api/compare
    API->>Pipe: Pipeline.run(query)
    Pipe->>Guard: input guardrail chain

    alt bị chặn (injection / heuristics)
        Guard-->>Pipe: block(reason)
        Pipe-->>API: raise InputGuardrailBlocked
        API-->>User: 422 (lý do bằng tiếng Việt)
    else allow / sanitize
        Guard-->>Pipe: query đã sanitize

        alt RECOMMEND
            Pipe->>Pipe: UserIntentParser.parse(query)
            Pipe->>Pipe: FilterEngine.extract(query)
            Pipe->>VDB: query(vector, filters)
            VDB-->>Pipe: candidates
            Pipe->>Pipe: CrossEncoderReranker.rerank(candidates)
            Pipe->>Pipe: ProductScorer.score(candidates)
        else COMPARE
            Pipe->>VDB: fetch products (theo query hoặc product_ids)
            VDB-->>Pipe: products
            Pipe->>Pipe: SpecAligner.align(products)
            Pipe->>Pipe: ComparisonFormatter.format(aligned)
        end

        Pipe->>Guard: context guardrail (sanitize dữ liệu sản phẩm)
        Guard-->>Pipe: context đã sanitize
        Pipe->>LLM: generate(prompt_with_context)
        LLM-->>Pipe: raw text response
        Pipe->>Pipe: ResponseParser.parse(raw)
        Pipe->>Guard: output guardrail (validate schema + grounding)

        alt hợp lệ & grounded
            Guard-->>Pipe: sanitized_payload
        else JSON/schema không hợp lệ, hoặc rỗng sau grounding
            Guard-->>Pipe: block(reason)
            Pipe->>Pipe: fallback tất định (không gọi lại LLM)
        end

        Pipe-->>API: {result, warnings[]}
        API-->>User: 200 JSON Response
    end
```

## Các tầng cốt lõi

### 1. Ingestion (`src/ingestion/`)

Nạp dữ liệu sản phẩm thô (JSON, CSV), làm sạch và chuẩn hóa, sau đó tách mỗi sản phẩm thành các chunk theo trường (mô tả, thông số, ưu/nhược điểm, đánh giá). Mỗi chunk mang theo metadata (product_id, brand, category, price) để phục vụ lọc.

### 2. Embedding (`src/embedding/`)

Chuyển các đoạn văn bản thành vector embedding bằng model `text-embedding-3-small` của OpenAI. Lưu vector vào Postgres (pgvector) với chỉ mục HNSW cosine similarity. Hỗ trợ embedding đa trường (multi-field) để truy xuất phong phú hơn.

### 3. Retrieval (`src/retrieval/`)

Với một truy vấn của người dùng, tầng retrieval trích xuất filter từ ngôn ngữ tự nhiên (khoảng giá, thương hiệu, danh mục), thực hiện hybrid search — semantic (pgvector) hợp nhất với BM25 keyword search (Elasticsearch ở production, in-memory làm fallback) qua Reciprocal Rank Fusion, cùng bộ filter pre-apply trên cả hai nhánh — tính composite score (độ tương đồng ngữ nghĩa, độ khớp giá, rating, độ phổ biến), và tùy chọn rerank bằng cross-encoder. Xem [Truy xuất lai](hybrid-retrieval.vi.md).

### 4. Generation (`src/generation/`)

Lấy các sản phẩm đã truy xuất cùng ý định người dùng, điền vào prompt template, và gọi LLM (Claude hoặc GPT) để sinh phản hồi JSON có cấu trúc.

### Guardrails (`src/guardrails/`)

Một tầng cross-cutting, không dùng LLM, được nối vào cả hai pipeline tại ba điểm: **guardrail đầu vào** từ chối/làm sạch truy vấn thô trước khi truy xuất, **guardrail ngữ cảnh** sanitize dữ liệu sản phẩm đã truy xuất trước khi đưa vào prompt, và **guardrail đầu ra** validate JSON của LLM theo schema rồi grounding từng item với sản phẩm đã truy xuất — rơi về phản hồi tất định (không gọi lại LLM) khi thất bại thay vì trả lỗi. Xem [Guardrail](guardrails.vi.md) để biết chi tiết đầy đủ.

### 5. Catalog & CDC Sync (`src/catalog/`, `src/sync/`)

Bảng `product_catalog` (Postgres) là source of truth duy nhất. API CRUD (`/api/products`) chỉ ghi vào đó; Debezium bắt thay đổi row từ WAL vào Kafka, và hai worker (`scripts/sync_worker.py`) consume một stream có thứ tự duy nhất để giữ các index dẫn xuất luôn fresh: **indexer** cập nhật index keyword Elasticsearch, **embedding worker** cập nhật pgvector — chỉ re-embed khi trường mang text thay đổi (đổi giá/rating là update metadata rẻ, không gọi API embedding).

## Điều phối (`src/pipeline/`)

Tầng pipeline kết nối mọi thứ lại với nhau. `RAGRouter` phân loại các truy vấn đến (gợi ý, so sánh, thông tin, hybrid) và điều hướng tới pipeline phù hợp. Mỗi pipeline điều phối toàn bộ luồng từ truy vấn đến phản hồi.

### Service discovery (`src/registry/`)

Tách biệt với pipeline RAG: khi khởi động, `lifespan` của FastAPI trong
`api/app.py` gọi `src/registry/client.py:register_if_configured` để đăng ký
`{name: "rag-recommend", host, port: <GRPC_PORT>, health:
"http://<host>:<HTTP_PORT>/health"}` với `service-registry` của platform
(`REGISTRY_URL`), heartbeat mỗi ~10s và deregister khi shutdown. Port đăng ký
là port *gRPC* (port gateway gọi vào); `health` trỏ tới port HTTP. Bỏ qua
đăng ký hoàn toàn nếu `REGISTRY_URL` chưa set — service vẫn chạy độc lập
bình thường.

## Xem thêm

- [Mô hình C4](c4-model.vi.md) — sơ đồ Context, Container, và Component của hệ thống.
- [Luồng dữ liệu](data-flow.vi.md) — định dạng dữ liệu và nơi lưu trữ khi di chuyển qua ingestion và xử lý theo request.
- [Truy xuất lai](hybrid-retrieval.vi.md) — hợp nhất semantic + BM25, và cách CDC giữ cả hai index luôn fresh.
- [Guardrail](guardrails.vi.md) — validate input/context/output, grounding, và chính sách fallback tất định.
