"""Unit tests for api/schemas.py request validators (schema-level guardrail)."""

import pytest
from pydantic import ValidationError

from api.schemas import CompareRequest, RecommendRequest


def test_recommend_request_rejects_blank_query():
    with pytest.raises(ValidationError):
        RecommendRequest(query="   ")


def test_recommend_request_rejects_too_long_query():
    with pytest.raises(ValidationError):
        RecommendRequest(query="a" * 2001)


def test_recommend_request_rejects_top_k_out_of_range():
    with pytest.raises(ValidationError):
        RecommendRequest(query="dien thoai", top_k=0)
    with pytest.raises(ValidationError):
        RecommendRequest(query="dien thoai", top_k=11)


def test_recommend_request_rejects_unknown_filter_key():
    with pytest.raises(ValidationError):
        RecommendRequest(query="dien thoai", filters={"unknown_key": "x"})


def test_recommend_request_accepts_whitelisted_filters():
    req = RecommendRequest(query="dien thoai", filters={"brand": "Samsung", "price_max": 15000000})
    assert req.filters["brand"] == "Samsung"


def test_compare_request_requires_query_or_product_ids():
    with pytest.raises(ValidationError):
        CompareRequest()


def test_compare_request_accepts_query_only():
    req = CompareRequest(query="so sanh iphone va samsung")
    assert req.query


def test_compare_request_normalizes_and_dedupes_product_ids():
    req = CompareRequest(product_ids=[" p-1 ", "p-1", "p-2"])
    assert req.product_ids == ["p-1", "p-2"]


def test_compare_request_rejects_invalid_product_id_chars():
    with pytest.raises(ValidationError):
        CompareRequest(product_ids=["p 1; DROP TABLE"])


def test_compare_request_rejects_too_many_product_ids():
    with pytest.raises(ValidationError):
        CompareRequest(product_ids=[f"p-{i}" for i in range(10)])
