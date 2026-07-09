"""Tests for ProductRetriever's query-rewriter wiring (no real embedder/DB)."""

from src.retrieval.filter_engine import FilterEngine
from src.retrieval.product_retriever import ProductRetriever
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.similarity_scorer import SimilarityScorer


class FakeEmbedder:
    """Returns a fixed vector per input text so calls can be counted."""

    def __init__(self):
        self.calls: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0]


class FakeVectorStore:
    """Returns canned results per query vector index (call order)."""

    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.where_clauses: list[dict | None] = []
        self._call = 0

    def query(self, query_embedding, n_results, where=None):
        self.where_clauses.append(where)
        response = self.responses[min(self._call, len(self.responses) - 1)]
        self._call += 1
        return response


def _chroma_style(
    ids: list[str], docs: list[str], metadatas: list[dict], distances: list[float]
) -> dict:
    return {
        "ids": [ids],
        "documents": [docs],
        "metadatas": [metadatas],
        "distances": [distances],
    }


def test_retrieve_without_rewriter_embeds_once():
    embedder = FakeEmbedder()
    store = FakeVectorStore(
        [
            _chroma_style(["p1"], ["doc1"], [{"name": "P1"}], [0.1]),
        ]
    )
    retriever = ProductRetriever(embedder=embedder, vector_store=store)

    results = retriever.retrieve("điện thoại samsung", top_k=5)

    assert len(embedder.calls) == 1
    assert results[0]["id"] == "p1"


def test_retrieve_with_rewriter_extracts_filters_from_corrected_query():
    embedder = FakeEmbedder()
    store = FakeVectorStore(
        [
            _chroma_style(["p1"], ["doc1"], [{"brand": "Samsung"}], [0.1]),
        ]
    )
    retriever = ProductRetriever(
        embedder=embedder,
        vector_store=store,
        filter_engine=FilterEngine(),
        scorer=SimilarityScorer(),
        query_rewriter=QueryRewriter(),
    )

    retriever.retrieve("dt sam sung gia re", top_k=5)

    # TypoCorrector fixed "dt" -> "điện thoại" and "sam sung" -> "samsung", so
    # FilterEngine (which runs on the rewritten query) detected both the
    # category (from "điện thoại") and the brand filter.
    assert store.where_clauses[0] == {"$and": [{"brand": "Samsung"}, {"category": "smartphone"}]}


def test_retrieve_fans_out_multi_query_and_merges_best_score():
    embedder = FakeEmbedder()
    # First variant call finds p1 with a low score, second finds p1 again
    # with a higher score plus a new product p2.
    store = FakeVectorStore(
        [
            _chroma_style(["p1"], ["doc1"], [{}], [0.5]),  # score 0.5
            _chroma_style(["p1", "p2"], ["doc1", "doc2"], [{}, {}], [0.1, 0.2]),  # 0.9, 0.8
        ]
    )
    rewriter = QueryRewriter(max_variants=2)
    retriever = ProductRetriever(embedder=embedder, vector_store=store, query_rewriter=rewriter)

    results = retriever.retrieve("cho tôi cái điện thoại pin trâu", top_k=5)

    assert len(embedder.calls) == 2  # one embed call per query variant
    ids = {r["id"] for r in results}
    assert ids == {"p1", "p2"}
    # SimilarityScorer.compute_score() with empty metadata/filters is
    # semantic * 0.5 + 0.1 (price_match defaults to 0.5, rating/popularity
    # are 0). distance 0.5 -> semantic 0.5 -> 0.35; distance 0.1 -> semantic
    # 0.9 -> 0.55. The merge ke
