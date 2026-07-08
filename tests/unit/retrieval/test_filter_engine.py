"""Tests for FilterEngine."""
from src.retrieval.filter_engine import FilterEngine


def test_extract_price():
    engine = FilterEngine()
    filters = engine.extract_filters("điện thoại tầm 15 triệu")
    assert "price_min" in filters
    assert "price_max" in filters

def test_extract_brand():
    engine = FilterEngine()
    filters = engine.extract_filters("điện thoại Samsung giá rẻ")
    assert filters.get("brand") == "Samsung"

def test_extract_category():
    engine = FilterEngine()
    filters = engine.extract_filters("laptop cho sinh viên")
    assert filters.get("category") == "laptop"

def test_extract_price_english_under():
    engine = FilterEngine()
    filters = engine.extract_filters("phone with great camera under 15 million VND")
    assert filters.get("price_max") == 15_000_000
    assert "price_min" not in filters

def test_extract_price_english_range():
    engine = FilterEngine()
    filters = engine.extract_filters("laptop from 10 to 20 million")
    assert filters.get("price_min") == 10_000_000
    assert filters.get("price_max") == 20_000_000
