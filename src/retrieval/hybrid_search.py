"""
Hybrid Search - Combine semantic search (pgvector) with keyword search (BM25)
via Reciprocal Rank Fusion, while enforcing the same metadata filters on both.
"""
import logging
from typing import Any

from src.retrieval.keyword_search import BM25Index
from src.retrieval.product_retriever import ProductRetriever

logger = logging.getLogger(__name__)


class HybridSearch:
    """Fuse dense (semantic) and sparse (BM25) retrieval with RRF.

    - Semantic branch: ``ProductRetriever.retrieve`` (embedding + pgvector
      cosine + SQL metadata filters + SimilarityScorer).
    - Keyword branch: in-memory :class:`BM25Index` over the same documents,
      with the extracted filters re-applied in Python so both branches see
      the same constraint set (e.g. budget).
    - Fusion: Reciprocal Rank Fusion, ``score(d) = sum(1 / (rrf_k + rank))``.
      RRF is rank-based, so the incomparable score scales of cosine similarity
      and BM25 never need calibration.
    """

    def __init__(
        self,
        retriever: ProductRetriever,
        bm25_index: BM25Index | None = None,
        rrf_k: int = 60,
        keyword_candidates: int = 50,
    ):
        self.retriever = retriever
        self.bm25 = bm25_index or BM25Index()
        self.rrf_k = rrf_k
        self.keyword_candidates = keyword_candidates

    def setup(self) -> None:
        """Build the BM25 index from the vector store's current documents."""
        corpus = self.retriever.vector_store.list_documents()
        self.bm25.build(corpus["ids"], corpus["documents"], corpus["metadatas"])
        logger.info("BM25 index built over %d documents", self.bm25.size)

    def retrieve(self, query: str, top_k: int = 10) -> list[dict]:
        """Alias so HybridSearch is a drop-in replacement for ProductRetriever."""
        return self.search(query, top_k=top_k)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Hybrid retrieval: semantic + BM25, fused with RRF."""
        semantic = self.retriever.retrieve(query, top_k=top_k)

        if self.bm25.size == 0:
            # No keyword index (empty store / setup not run): semantic only.
            return semantic

        filters = self.retriever.filter_engine.extract_filters(query)
        keyword = [
            c
            for c in self.bm25.search(query, top_k=self.keyword_candidates)
            if self._matches_filters(c.get("metadata") or {}, filters)
        ]

        return self._rrf_merge(semantic, keyword)[:top_k]

    def _rrf_merge(self, semantic: list[dict], keyword: list[dict]) -> list[dict]:
        """Reciprocal Rank Fusion over the two ranked lists (by document id)."""
        merged: dict[str, dict] = {}
        for rank, candidate in enumerate(semantic):
            entry = merged.setdefault(candidate["id"], dict(candidate))
            entry["rrf_score"] = entry.get("rrf_score", 0.0) + 1 / (self.rrf_k + rank + 1)
        for rank, candidate in enumerate(keyword):
            entry = merged.setdefault(candidate["id"], dict(candidate))
            entry["rrf_score"] = entry.get("rrf_score", 0.0) + 1 / (self.rrf_k + rank + 1)
            entry["bm25_score"] = candidate["bm25_score"]

        results = list(merged.values())
        for entry in results:
            # Keyword-only hits have no semantic score; downstream scorers
            # expect the key to exist.
            entry.setdefault("score", 0.0)
            entry["rrf_score"] = round(entry["rrf_score"], 6)
        results.sort(key=lambda x: x["rrf_score"], reverse=True)
        return results

    @staticmethod
    def _matches_filters(metadata: dict, filters: dict[str, Any]) -> bool:
        """Re-apply extracted filters to BM25 hits (Python-side).

        Mirrors the SQL WHERE clause the semantic branch pushes to pgvector,
        so over-budget or wrong-brand products cannot enter via the keyword
        branch.
        """

        def as_float(value: Any) -> float | None:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        brand = filters.get("brand")
        if brand and str(metadata.get("brand", "")).lower() != str(brand).lower():
            return False
        category = filters.get("category")
        if category and str(metadata.get("category", "")).lower() != str(category).lower():
            return False

        price = as_float(metadata.get("price"))
        if "price_min" in filters and (price is None or price < filters["price_min"]):
            return False
        if "price_max" in filters and (price is None or price > filters["price_max"]):
            return False

        if "min_rating" in filters:
            rating = as_float(metadata.get("avg_rating"))
            if rating is None or rating < filters["min_rating"]:
                return False
        return True
