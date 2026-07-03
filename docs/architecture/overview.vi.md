# Tổng quan kiến trúc

Hệ thống tuân theo kiến trúc RAG tiêu chuẩn với bốn tầng cốt lõi:

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
        EMBED --> VDB[("ChromaDB\nvector + metadata")]
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
    participant VDB as ChromaDB
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

Chuyển các đoạn văn bản thành vector embedding bằng model `text-embedding-3-small` của OpenAI. Lưu vector vào ChromaDB với chỉ mục cosine similarity. Hỗ trợ embedding đa trường (multi-field) để truy xuất phong phú hơn.

### 3. Retrieval (`src/retrieval/`)

Với một truy vấn của người dùng, tầng retrieval trích xuất filter từ ngôn ngữ tự nhiên (khoảng giá, thương hiệu, danh mục), thực hiện hybrid search (semantic + metadata), tính composite score (độ tương đồng ngữ nghĩa, độ khớp giá, rating, độ phổ biến), và tùy chọn rerank bằng cross-encoder.

### 4. Generation (`src/generation/`)

Lấy các sản phẩm đã truy xuất cùng ý định người dùng, điền vào prompt template, và gọi LLM (Claude hoặc GPT) để sinh phản hồi JSON có cấu trúc. Bao gồm các guardrail để validate input và kiểm tra an toàn output.

## Điều phối (`src/pipeline/`)

Tầng pipeline kết nối mọi thứ lại với nhau. `RAGRouter` phân loại các truy vấn đến (gợi ý, so sánh, thông tin, hybrid) và điều hướng tới pipeline phù hợp. Mỗi pipeline điều phối toàn bộ luồng từ truy vấn đến phản hồi.
