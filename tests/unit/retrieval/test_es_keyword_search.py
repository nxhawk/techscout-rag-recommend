"""Unit tests for the ES keyword backend (query building + HybridSearch wiring)."""

from src.retrieval.es_keyword_search import build_bool_query
from src.retrieval.hybrid_search import HybridSearch


class TestBuildBoolQuery:
    def test_no_filters(self):
        query = build_bool_query("điện thoại pin trâu", None)
        assert query["bool"]["must"] == [{"match": {"document": {"query": "điện thoại pin trâu"}}}]
        assert query["bool"]["filter"] == []

    def test_all_filters_become_prefilter_clauses(self):
        filters = {
            "brand": "Samsung",
            "category": "smartphone",
            "price_min": 8_000_000,
            "price_max": 12_000_000,
            "min_rating": 4.0,
        }
        clauses = build_bool_query("q", filters)["bool"]["filter"]
        assert {"term": {"brand": "samsung"}} in clauses
        assert {"term": {"category": "smartphone"}} in clauses
        assert {"range": {"price": {"gte": 8_000_000, "lte": 12_000_000}}} in clauses
        assert {"range": {"avg_rating": {"gte": 4.0}}} in clauses

    def test_price_max_only(self):
        clauses = build_bool_query("q", {"price_max": 5_000_000})["bool"]["filter"]
        assert clauses == [{"range": {"price": {"lte": 5_000_000}}}]


class _PrefilterBackend:
    """Fake keyword backend with ES semantics (prefilters=True)."""

    prefilters = True

    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.received_filters = None

    def search(self, query, top_k=50, filters=None):
        if self.error:
            raise self.error
        self.received_filters = filters
        return self.results


class _FakeRetriever:
    """Semantic branch stub: fixed results + real FilterEngine."""

    def __init__(self, results):
        from src.retrieval.filter_engine import FilterEngine

        self.results = results
        self.filter_engine = FilterEngine()

    def retrieve(self, query, top_k=10, intent_hints=None):
        return self.results


class TestHybridSearchWithPrefilterBackend:
    SEMANTIC = [{"id": "a_description", "score": 0.9, "metadata": {}}]
    KEYWORD = [{"id": "b_description", "document": "d", "metadata": {}, "bm25_score": 3.2}]

    def test_filters_are_passed_to_backend(self):
        backend = _PrefilterBackend(results=self.KEYWORD)
        searcher = HybridSearch(_FakeRetriever(self.SEMANTIC), bm25_index=backend)
        results = searcher.search("điện thoại samsung dưới 10 triệu", top_k=5)

        assert backend.received_filters["brand"] == "Samsung"
        assert backend.received_filters["category"] == "smartphone"
        assert backend.received_filters["price_max"] == 10_000_000
        ids = {r["id"] for r in results}
        assert ids == {"a_description", "b_description"}
        assert all("rrf_score" in r for r in results)

    def test_backend_failure_degrades_to_semantic_only(self):
        backend = _PrefilterBackend(error=ConnectionError("ES down"))
        searcher = HybridSearch(_FakeRetriever(self.SEMANTIC), bm25_index=backend)
        results = searcher.search("điện thoại", top_k=5)
        assert results == self.SEMANTIC

    def test_setup_is_noop_for_prefilter_backend(self):
        backend = _PrefilterBackend()
        searcher = HybridSearch(_FakeRetriever(self.SEMANTIC), bm25_index=backend)
        searcher.setup()  # must not raise / must not requ
