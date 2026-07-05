# Testing

## Chạy Test

```bash
# Chạy toàn bộ test
uv run pytest tests/

# Chỉ chạy unit test
uv run pytest tests/unit/

# Chỉ chạy integration test
uv run pytest tests/integration/

# Chạy với output verbose
uv run pytest tests/ -v

# Chạy một file test cụ thể
uv run pytest tests/unit/test_filter_engine.py
```

## Cấu trúc Test

```
tests/
├── conftest.py                     # Fixture dùng chung (sample_product, sample_products)
├── unit/                           # Test nhanh, độc lập (không cần network / secrets)
│   ├── test_router.py              # Phân loại truy vấn của RAGRouter
│   ├── test_chunker.py             # Output của ProductChunker
│   ├── test_filter_engine.py       # Trích xuất của FilterEngine
│   ├── test_es_keyword_search.py   # Dựng truy vấn keyword Elasticsearch
│   ├── test_hybrid_search.py       # Fusion RRF + áp filter của HybridSearch
│   ├── test_vector_store_filters.py # Filter metadata SQL của vector store
│   ├── test_products_api.py        # Route CRUD /api/products
│   ├── test_recommend_route.py     # Route /api/recommend
│   ├── test_sync_events.py         # Parse event Debezium + phát hiện thay đổi
│   └── test_sync_workers.py        # Các CDC sync worker (SearchIndexer, EmbeddingSyncer)
└── integration/                    # Dành cho test cần dịch vụ ngoài (chưa có test)
```

Các test được nhóm thành: **routing/chunking/filter** (`test_router`, `test_chunker`,
`test_filter_engine`); **retrieval** (`test_es_keyword_search`, `test_hybrid_search`,
`test_vector_store_filters`); **API** (`test_products_api`, `test_recommend_route`);
và **CDC sync** (`test_sync_events`, `test_sync_workers`). `tests/integration/` dành
cho các test cần dịch vụ ngoài thật và hiện chưa có test nào.

## Viết Test

Dùng fixture pytest từ `conftest.py` cho dữ liệu mẫu:

```python
def test_chunker_output(sample_product):
    from src.ingestion.chunker import ProductChunker

    chunker = ProductChunker()
    chunks = chunker.chunk_product(sample_product)

    assert len(chunks) >= 2
    assert all("product_id" in c for c in chunks)
```

### Test các CDC sync worker

Tầng CDC được test hoàn toàn offline nên chạy được trong CI mà **không cần Kafka,
ES, DB, secrets hay network**:

- **`test_sync_events.py`** phủ phần xử lý event Debezium — `parse_debezium_message`,
  `content_hash` của các trường chứa văn bản, phát hiện `text_changed`, và các
  `metadata_fields` kích hoạt cập nhật metadata-only thay vì re-embed.
- **`test_sync_workers.py`** kiểm thử hai worker (`SearchIndexer` và
  `EmbeddingSyncer`) dựa trên **fakes trong bộ nhớ** (`FakeES`, `FakeVectorStore`,
  `FakeEmbedder`). Không dùng Kafka/ES/DB thật, nên logic phát hiện thay đổi được
  kiểm chứng mà không cần dịch vụ chạy thật.

## Đánh giá (Evaluation)

Các script đánh giá chất lượng RAG nằm trong `evaluation/`:

```bash
# Chạy đánh giá gợi ý
uv run python evaluation/eval_recommend.py

# Chạy đánh giá so sánh
uv run python evaluation/eval_compare.py
```

Test case được định nghĩa trong `evaluation/test_cases.json`.
