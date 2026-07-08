"""Tests for RAGRouter."""
from src.pipeline.rag_router import RAGRouter, QueryType


def test_recommend_query():
    router = RAGRouter()
    assert router.route("Gợi ý điện thoại chụp ảnh đẹp") == QueryType.RECOMMEND

def test_compare_query():
    router = RAGRouter()
    assert router.route("So sánh iPhone 15 và Samsung S24") == QueryType.COMPARE

def test_info_query():
    router = RAGRouter()
    assert router.route("Thông số iPhone 15 Pro Max") == QueryType.INFO
