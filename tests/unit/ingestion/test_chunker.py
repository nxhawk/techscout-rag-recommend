"""Tests for ProductChunker."""
from src.ingestion.chunker import ProductChunker


def test_chunk_product():
    chunker = ProductChunker()
    product = {
        "product_id": "test-001",
        "name": "Test Phone",
        "brand": "TestBrand",
        "category": "smartphone",
        "price": 10000000,
        "description": "A test phone for testing.",
        "specifications": {"ram": "8 GB", "storage": "128 GB"},
        "pros": ["Good battery"],
        "cons": ["Average camera"],
        "review_summary": "Users like the battery life.",
        "avg_rating": 4.2,
        "review_count": 100,
    }
    chunks = chunker.chunk_product(product)
    assert len(chunks) == 4  # description, specs, pros_cons, review
    assert all("product_id" in c for c in chunks)
    assert all("chunk_type" in c for c in chunks)
    # Required by the recommend pipeline's LLM context builder.
    assert all(c["name"] == "Test Phone" for c in chunks)
    assert all(c["avg_rating"] == 4.2 for c in chunks)
    assert all(c["price"] == 10000000 for c in chunks)
