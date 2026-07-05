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
        Q[Truy vấn người dùng] --> GIN["Guardrails\n(kiểm tra input)"]
        GIN --> ROUTER{RAG Router}

        ROUTER -->|RECOMMEND| RI[UserIntentParser]
        RI --> RF[FilterEngine]
        RF --> RR[ProductRetriever]
        RR --> RRK[CrossEncoderReranker]
        RRK --> RSC[ProductScorer]

        ROUTER -->|COMPARE| CX[Trích xuất sản phẩm]
        CX --> CR[ProductRetriever]
        CR --> CAL[SpecAligner]
        CAL --> CFM[ComparisonFormatter]

        RSC --> LLM["LLM Client\n(Anthropic / OpenAI / Gemini)"]
        CFM --> LLM
        LLM --> RP[ResponseParser]
        RP --> GOUT["Guardrails\n(kiểm tra output)"]
        GOUT --> RESP[JSON Response]
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
    participant Guard as Guardrails
    participant Router as RAGRouter
    participant Pipe as Recommend/Compare Pipeline
    participant VDB as Postgres (pgvector)
    participant LLM as LLM Client

    User->>API: POST /api/recommend hoặc /api/compare
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
        Pipe->>VDB: fetch products (theo query hoặc product_ids)
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

## Các tầng cốt lõi

### 1. Ingestion (`src/ingestion/`)

Nạp dữ liệu sản phẩm thô (JSON, CSV), làm sạch và chuẩn hóa, sau đó tách mỗi sản phẩm thành các chunk theo trường (mô tả, thông số, ưu/nhược điểm, đánh giá). Mỗi chunk mang theo metadata (product_id, brand, category, price) để phục vụ lọc.

### 2. Embedding (`src/embedding/`)

Chuyển các đoạn văn bản thành vector embedding bằng model `text-embedding-3-small` của OpenAI. Lưu vector vào Postgres (pgvector) với chỉ mục HNSW cosine similarity. Hỗ trợ embedding đa trường (multi-field) để truy xuất phong phú hơn.

### 3. Retrieval (`src/retrieval/`)

Với một truy vấn của người dùng, tầng retrieval trích xuất filter từ ngôn ngữ tự nhiên (khoảng giá, thương hiệu, danh mục), thực hiện hybrid search — semantic (pgvector) hợp nhất với BM25 keyword search (Elasticsearch ở production, in-memory làm fallback) qua Reciprocal Rank Fusion, cùng bộ filter pre-apply trên cả hai nhánh — tính composite score (độ tương đồng ngữ nghĩa, độ khớp giá, rating, độ phổ biến), và tùy chọn rerank bằng cross-encoder. Xem [Truy xuất lai](hybrid-retrieval.vi.md).

### 4. Generation (`src/generation/`)

Lấy các sản phẩm đã truy xuất cùng ý định người dùng, điền vào prompt template, và gọi LLM (Claude hoặc GPT) để sinh phản hồi JSON có cấu trúc. Bao gồm các guardrail để validate input và kiểm tra an toàn output.

### 5. Catalog & CDC Sync (`src/catalog/`, `src/sync/`)

Bảng `product_catalog` (Postgres) là source of truth duy nhất. API CRUD (`/api/products`) chỉ ghi vào đó; Debezium bắt thay đổi row từ WAL vào Kafka, và hai worker (`scripts/sync_worker.py`) consume một stream có thứ tự duy nhất để giữ các index dẫn xuất luôn fresh: **indexer** cập nhật index keyword Elasticsearch, **embedding worker** cập nhật pgvector — chỉ re-embed khi trường mang text thay đổi (đổi giá/rating là update metadata rẻ, không gọi API embedding).

## Điều phối (`src/pipeline/`)

Tầng pipeline kết nối mọi thứ lại với nhau. `RAGRouter` phân loại các truy vấn đến (gợi ý, so sánh, thông tin, hybrid) và điều hướng tới pipeline phù hợp. Mỗi pipeline điều phối toàn bộ luồng từ truy vấn đến phản hồi.

## Xem thêm

- [Mô hình C4](c4-model.vi.md) — sơ đồ Context, Container, và Component của hệ thống.
- [Luồng dữ liệu](data-flow.vi.md) — định dạng dữ liệu và nơi lưu trữ khi di chuyển qua ingestion và xử lý theo request.
- [Truy xuất lai](hybrid-retrieval.vi.md) — hợp nhất semantic + BM25, và cách CDC giữ cả hai index luôn fresh.
