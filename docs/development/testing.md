# Testing

## Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run unit tests only
uv run pytest tests/unit/

# Run integration tests only
uv run pytest tests/integration/

# Run with verbose output
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/unit/test_filter_engine.py
```

## Test Structure

```
tests/
├── conftest.py                     # Shared fixtures (sample_product, sample_products)
├── unit/                           # Fast, isolated tests (no network / secrets)
│   ├── test_router.py              # RAGRouter query classification
│   ├── test_chunker.py             # ProductChunker output
│   ├── test_filter_engine.py       # FilterEngine extraction
│   ├── test_es_keyword_search.py   # Elasticsearch keyword query building
│   ├── test_hybrid_search.py       # HybridSearch RRF fusion + filter enforcement
│   ├── test_vector_store_filters.py # Vector store SQL metadata filters
│   ├── test_products_api.py        # /api/products CRUD route
│   ├── test_recommend_route.py     # /api/recommend route
│   ├── test_sync_events.py         # Debezium event parsing + change detection
│   └── test_sync_workers.py        # CDC sync workers (SearchIndexer, EmbeddingSyncer)
└── integration/                    # For services-backed tests (no tests yet)
```

The tests group into: **routing/chunking/filters** (`test_router`, `test_chunker`,
`test_filter_engine`); **retrieval** (`test_es_keyword_search`, `test_hybrid_search`,
`test_vector_store_filters`); **API** (`test_products_api`, `test_recommend_route`);
and **CDC sync** (`test_sync_events`, `test_sync_workers`). `tests/integration/` is
reserved for tests that need real external services and currently holds no tests.

## Writing Tests

Use pytest fixtures from `conftest.py` for sample data:

```python
def test_chunker_output(sample_product):
    from src.ingestion.chunker import ProductChunker

    chunker = ProductChunker()
    chunks = chunker.chunk_product(sample_product)

    assert len(chunks) >= 2
    assert all("product_id" in c for c in chunks)
```

### Testing the CDC sync workers

The CDC layer is tested entirely offline so it runs in CI with **no Kafka, ES, DB,
secrets, or network**:

- **`test_sync_events.py`** covers Debezium event handling — `parse_debezium_message`,
  the `content_hash` of the text-bearing fields, `text_changed` detection, and the
  `metadata_fields` that trigger a metadata-only update rather than a re-embed.
- **`test_sync_workers.py`** exercises the two workers (`SearchIndexer` and
  `EmbeddingSyncer`) against **in-memory fakes** (`FakeES`, `FakeVectorStore`,
  `FakeEmbedder`). No real Kafka/ES/DB is involved, so the change-detection logic
  is verified without any live service.

## Evaluation

RAG quality evaluation scripts are in `evaluation/`:

```bash
# Run recommendation evaluation
uv run python evaluation/eval_recommend.py

# Run comparison evaluation
uv run python evaluation/eval_compare.py
```

Test cases are defined in `evaluation/test_cases.json`.
