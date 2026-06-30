"""Shared test fixtures."""
import pytest


@pytest.fixture
def sample_product():
    """A sample product for testing."""
    return {
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
        "tags": ["test"],
    }


@pytest.fixture
def sample_products(sample_product):
    """Multiple sample products for comparison testing."""
    product_b = {
        **sample_product,
        "product_id": "test-002",
        "name": "Test Phone Pro",
        "price": 15000000,
        "avg_rating": 4.5,
    }
    return [sample_product, product_b]
