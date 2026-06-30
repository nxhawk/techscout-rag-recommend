"""
Hybrid Search - Kết hợp semantic search + keyword search + metadata filter.
"""
from src.retrieval.product_retriever import ProductRetriever


class HybridSearch:
    """Combine semantic, keyword, and metadata-based search."""

    def __init__(self, retriever: ProductRetriever):
        self.retriever = retriever

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Perform hybrid search combining multiple strategies."""
        # Semantic search via retriever
        results = self.retriever.retrieve(query, top_k=top_k)

        # TODO: Add keyword-based search (BM25) for exact matches
        # TODO: Merge and deduplicate results from both strategies

        return results
