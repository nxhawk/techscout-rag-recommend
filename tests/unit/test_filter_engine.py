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
