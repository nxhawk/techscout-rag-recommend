"""Reranker - Cross-encoder reranking sau initial retrieval."""
from typing import Protocol


class RerankerBackend(Protocol):
    """Protocol for reranker implementations."""

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        ...


class CrossEncoderReranker:
    """Rerank retrieved results using a cross-encoder model.

    Cross-encoders score (query, document) pairs jointly,
    producing more accurate relevance scores than bi-encoder similarity.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        top_k: int = 10,
    ):
        self.model_name = model_name
        self.top_k = top_k
        self.model = None

    def setup(self) -> None:
        """Load the cross-encoder model (lazy init)."""
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(self.model_name)
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for reranking. "
                "Install with: uv add sentence-transformers"
            )

    def rerank(self, query: str, candidates: list[dict], top_k: int | None = None) -> list[dict]:
        """Rerank candidates by cross-encoder score.

        Args:
            query: The user query.
            candidates: List of dicts with at least a 'document' key.
            top_k: Override default top_k.

        Returns:
            Reranked list of candidates with 'rerank_score' added.
        """
        k = top_k or self.top_k
        if not candidates:
            return []

        if self.model is None:
            # Fallback: return candidates as-is if model not loaded
            return candidates[:k]

        pairs = [(query, c.get("document", "")) for c in candidates]
        scores = self.model.predict(pairs)

        for candidate, score in zip(candidates, scores):
            candidate["rerank_score"] = float(score)

        reranked = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:k]
