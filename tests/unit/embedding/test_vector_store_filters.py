"""Tests for VectorStore metadata-filter SQL building (no DB required)."""

from src.embedding.vector_store import VectorStore


def make_store() -> VectorStore:
    # No setup() call: _build_where_sql does not touch the connection.
    return VectorStore(collection_name="products", embedding_dim=768)


def test_no_filter():
    sql, params = make_store()._build_where_sql(None)
    assert sql == ""
    assert params == []


def test_equality_filter():
    sql, params = make_store()._build_where_sql({"brand": "Apple"})
    assert sql == "WHERE metadata->>%s = %s"
    assert params == ["brand", "Apple"]


def test_numeric_range_filter():
    sql, params = make_store()._build_where_sql({"price": {"$lte": 15_000_000}})
    assert sql == "WHERE (metadata->>%s)::numeric <= %s"
    assert params == ["price", 15_000_000]


def test_and_composite_with_range():
    sql, params = make_store()._build_where_sql(
        {"$and": [{"category": "smartphone"}, {"price": {"$gte": 5_000_000, "$lte": 15_000_000}}]}
    )
    assert sql == (
        "WHERE metadata->>%s = %s"
        " AND (metadata->>%s)::numeric >= %s"
        " AND (metadata->>%s)::numeric <= %s"
    )
    assert params == ["category", "smartphone", "price", 5_000_000, "price", 15_000_000]


def test_unknown_operator_is_ignored():
    sql, params = make_store()._build_where_sql({"price": {"$evil": "1; DROP TABLE x"}})
    assert sql == ""
    assert params == []
