"""
Product Retriever - Kết hợp filter + search để trả về sản phẩm phù hợp.
"""
from src.embedding.product_embedder import ProductEmbedder
from src.embedding.vector_store import VectorStore
from src.retrieval.filter_engine import FilterEngine
from src.retrieval.similarity_scorer import SimilarityScorer


class ProductRetriever:
    """Retrieve relevant products using hybrid search + filtering."""

    def __init__(
        self,
        embedder: ProductEmbedder,
        vector_store: VectorStore,
        filter_engine: FilterEngine | None = None,
        scorer: SimilarityScorer | None = None,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.filter_engine = filter_engine or FilterEngine()
        self.scorer = scorer or SimilarityScorer()

    def retrieve(self, query: str, top_k: int = 10) -> list[dict]:
        """Retrieve top-K relevant products for a query."""
        # Step 1: Extract filters
        filters = self.filter_engine.extract_filters(query)

        # Step 2: Embed query
        query_embedding = self.embedder.embed_text(query)

        # Step 3: Query vector store with metadata filters
        where_clause = self._build_where_clause(filters)
        results = self.vector_store.query(
            query_embedding=query_embedding,
            n_results=top_k * 2,
            where=where_clause,
        )

        # Step 4: Score and rank results
        scored = self._score_results(results, filters)
        scored.sort(key=lambda x: x["score"], reverse=True)

        return scored[:top_k]

    def _build_where_clause(self, filters: dict) -> dict | None:
        conditions = []
        if "brand" in filters:
            conditions.append({"brand": filters["brand"]})
        if "category" in filters:
            conditions.append({"category": filters["category"]})
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
            scored.append({
                "id": doc_id,
                "document": results["documents"][0][i] if results.get("documents") else "",
                "metadata": metadata,
                "score": score,
            })
        return scored
