"""Unit tests for BM25 keyword search, hybrid RRF fusion and reranker wiring."""

from src.pipeline.recommend.engine import RecommendEngine
from src.retrieval.filter_engine import FilterEngine
from src.retrieval.hybrid_search import HybridSearch
from src.retrieval.keyword_search import BM25Index, tokenize
from src.retrieval.reranker import CrossEncoderReranker


def make_index(docs: dict[str, tuple[str, dict]]) -> BM25Index:
    index = BM25Index()
    ids = list(docs.keys())
    index.build(
        ids,
        [docs[i][0] for i in ids],
        [docs[i][1] for i in ids],
    )
    return index


class FakeRetriever:
    """Semantic branch stand-in with fixed, ordered results."""

    def __init__(self, results: list[dict]):
        self.results = results
        self.filter_engine = FilterEngine()
        self.vector_store = None

    def retrieve(self, query: str, top_k: int = 10) -> list[dict]:
        return self.results[:top_k]


def candidate(doc_id: str, score: float = 0.5, metadata: dict | None = None) -> dict:
    return {"id": doc_id, "document": doc_id, "metadata": metadata or {}, "score": score}


# ---------------------------------------------------------------- BM25 index


def test_tokenize_keeps_vietnamese_diacritics():
    assert tokenize("Điện thoại Xiaomi 14, pin TRÂU!") == [
        "điện", "thoại", "xiaomi", "14", "pin", "trâu",
    ]


def test_bm25_ranks_exact_term_match_first():
    index = make_index({
        "p1_specs": ("Xiaomi 14 camera Leica pin 4610mAh", {}),
        "p2_specs": ("Samsung Galaxy A55 man hinh AMOLED", {}),
        "p3_specs": ("iPhone 15 camera 48MP", {}),
    })
    hits = index.search("xiaomi 14")
    assert hits[0]["id"] == "p1_specs"
    assert hits[0]["bm25_score"] > 0
    # No-overlap documents are omitted entirely.
    assert all(h["id"] != "p2_specs" for h in hits)


def test_bm25_empty_query_or_corpus_returns_nothing():
    assert BM25Index().search("xiaomi") == []
    index = make_index({"p1": ("some text", {})})
    assert index.search("!!!") == []


# ------------------------------------------------------------- hybrid fusion


def test_hybrid_falls_back_to_semantic_when_index_empty():
    semantic = [candidate("a"), candidate("b")]
    hybrid = HybridSearch(FakeRetriever(semantic))
    assert hybrid.search("anything", top_k=2) == semantic


def test_rrf_boosts_document_found_by_both_branches():
    # Semantic order: a, b. BM25 finds b (plus c). Query has no brand/price
    # keywords, so no filters are extracted.
    retriever = FakeRetriever([candidate("a", 0.9), candidate("b", 0.8)])
    index = make_index({
        "b": ("điện thoại pin trâu", {}),
        "c": ("pin trâu sạc nhanh", {}),
    })
    hybrid = HybridSearch(retriever, bm25_index=index)
    results = hybrid.search("pin trâu", top_k=3)

    ids = [r["id"] for r in results]
    # b appears in both rankings -> highest RRF score.
    assert ids[0] == "b"
    assert set(ids) == {"a", "b", "c"}
    # Keyword-only hit still carries a semantic 'score' key for the scorer.
    c_entry = next(r for r in results if r["id"] == "c")
    assert c_entry["score"] == 0.0
    assert "bm25_score" in c_entry
    assert all("rrf_score" in r for r in results)


def test_bm25_branch_respects_extracted_filters():
    # Query has a budget ("dưới 15 triệu" -> price_max=15_000_000).
    retriever = FakeRetriever([])
    index = make_index({
        "cheap": (
            "điện thoại xiaomi pin tốt",
            {"price": 10_000_000, "brand": "Xiaomi", "category": "smartphone"},
        ),
        "expensive": (
            "điện thoại xiaomi pin tốt",
            {"price": 25_000_000, "brand": "Xiaomi", "category": "smartphone"},
        ),
    })
    hybrid = HybridSearch(retriever, bm25_index=index)
    results = hybrid.search("điện thoại xiaomi dưới 15 triệu", top_k=5)

    ids = [r["id"] for r in results]
    assert "cheap" in ids
    assert "expensive" not in ids


# ---------------------------------------------------------------- reranking


def test_reranker_without_model_passes_candidates_through():
    reranker = CrossEncoderReranker(top_k=2)
    cands = [candidate("a"), candidate("b"), candidate("c")]
    assert reranker.rerank("q", cands) == cands[:2]


class FakeReranker:
    """Deterministic reranker: reverses order and attaches logits."""

    def rerank(self, query: str, candidates: list[dict], top_k: int | None = None) -> list[dict]:
        reranked = list(reversed(candidates))
        for i, c in enumerate(reranked):
            c["rerank_score"] = float(len(reranked) - i)
        return reranked[: (top_k or len(reranked))]


def test_engine_uses_reranker_and_sigmoid_relevance():
    retriever = FakeRetriever([
        candidate("a", 0.9, {"name": "A"}),
        candidate("b", 0.1, {"name": "B"}),
    ])
    engine = RecommendEngine(retriever=retriever, reranker=FakeReranker())
    result = engine.recommend("điện thoại pin tốt", top_k=2)

    recs = result["recommendations"]
    assert len(recs) == 2
    # Reranker reversed the order: b got the highest rerank_score.
    assert recs[0]["id"] == "b"
    relevance = recs[0]["score_breakdown"]["relevance"]
    assert 0.0 < relevance < 1.0  # sigmoid-squashed logit, not the raw 0.1


def test_engine_without_reranker_keeps_retrieval_relevance():
    retriever = FakeRetriever([candidate("a", 0.9, {"name": "A"})])
    engine = RecommendEngine(retriever=retriever)
    result = engine.recommend("điện thoại", top_k=1)
    assert result["recommendations"][0]["score_breakdown"]["relevance"] == 0.9
