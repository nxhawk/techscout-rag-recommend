"""
Product Retriever - Kết hợp query rewrite + filter + search để trả về sản
phẩm phù hợp.
"""

from typing import Any

from src.embedding.product_embedder import ProductEmbedder
from src.embedding.vector_store import VectorStore
from src.retrieval.filter_engine import FilterEngine
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.similarity_scorer import SimilarityScorer


class ProductRetriever:
    """Retrieve relevant products using hybrid search + filtering."""

    def __init__(
        self,
        embedder: ProductEmbedder,
        vector_store: VectorStore,
        filter_engine: FilterEngine | None = None,
        scorer: SimilarityScorer | None = None,
        query_rewriter: QueryRewriter | None = None,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.filter_engine = filter_engine or FilterEngine()
        self.scorer = scorer or SimilarityScorer()
        # Optional (mirrors `reranker` in RecommendEngine): None means the
        # feature is off and `retrieve()` behaves exactly as before.
        self.query_rewriter = query_rewriter

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        intent_hints: dict[str, Any] | None = None,
    ) -> list[dict]:
        """Retrieve top-K relevant products for a query.

        ``intent_hints`` (optional) is the already-parsed intent from
        ``UserIntentParser`` (e.g. ``{"use_case": [...], "priorities": [...]}``),
        forwarded to the query rewriter's intent-aware step when a
        ``QueryRewriter`` is configured.
        """
        # Step 0: Rewrite the query (normalize/expand/intent-aware), and get
        # one or more query variants for multi-query retrieval.
        if self.query_rewriter is not None:
            rewrite = self.query_rewriter.rewrite(query, intent_hints=intent_hints)
            search_query = rewrite.rewritten_query
            variants = rewrite.query_variants or [search_query]
        else:
            search_query = query
            variants = [query]

        # Step 1: Extract filters (run on the rewritten query so typo
        # correction, e.g. "sam sung" -> "samsung", still yields a brand filter).
        filters = self.filter_engine.extract_filters(search_query)
        where_clause = self._build_where_clause(filters)

        # Step 2 & 3: Embed each query variant and query the vector store,
        # merging by keeping the best (max) score per product id. With a
        # single variant (the default) this is identical to the old
        # single-embed behavior.
        best_by_id: dict[str, dict] = {}
        for variant in variants:
            query_embedding = self.embedder.embed_text(variant)
            results = self.vector_store.query(
                query_embedding=query_embedding,
                n_results=top_k * 2,
                where=where_clause,
            )
            for candidate in self._score_results(results, filters):
                existing = best_by_id.get(candidate["id"])
                if existing is None or candidate["score"] > existing["score"]:
                    best_by_id[candidate["id"]] = candidate

        # Step 4: Rank merged results
        scored = list(best_by_id.values())
        scored.sort(key=lambda x: x["score"], reverse=True)

        return scored[:top_k]

    def _build_where_clause(self, filters: dict) -> dict | None:
        conditions: list[dict] = []
        if "brand" in filters:
            conditions.append({"brand": filters["brand"]})
        if "category" in filters:
            conditions.append({"category": filters["category"]})
        # Push the budget down to the vector store so over-budget products
        # never reach the LLM context (scoring alone only downranks them).
        price_range: dict = {}
        if "price_min" in filters:
            price_range["$gte"] = filters["price_min"]
        if "price_max" in filters:
            price_range["$lte"] = filters["price_max"]
        if price_range:
            conditions.append({"price": price_range})
        if "min_rating" in filters:
            conditions.append({"avg_rating": {"$gte": filters["min_rating"]}})
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _score_results(self, results: dict, filters: dict) -> list[dict]:
        scored = []
        if not results.get("ids") or not results["ids"][0]:
            return scored
        for i, doc_id in enumerate(results["ids"][0]):
            metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
            distance = results["distances"][0][i] if results.get("distances") else 0
            semantic_score = 1 - distance
            score = self.scorer.compute_score(semantic_score, metadata, filters)
            scored.append(
                {
                    "id": doc_id,
                    "document": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": metadata,
                    "score": score,
                }
            )
        return scored
