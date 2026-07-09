"""Recommend Engine - Logic gợi ý sản phẩm chính."""

import math

from src.pipeline.recommend.user_intent_parser import UserIntentParser
from src.pipeline.recommend.scoring import ProductScorer
from src.retrieval.hybrid_search import HybridSearch
from src.retrieval.product_retriever import ProductRetriever
from src.retrieval.reranker import CrossEncoderReranker


class RecommendEngine:
    """Main recommendation engine.

    Flow: intent parse -> retrieve (semantic or hybrid) -> optional
    cross-encoder rerank -> multi-criteria scoring -> top_k.
    """

    def __init__(
        self,
        retriever: ProductRetriever | HybridSearch,
        intent_parser: UserIntentParser | None = None,
        scorer: ProductScorer | None = None,
        reranker: CrossEncoderReranker | None = None,
    ):
        self.retriever = retriever
        self.intent_parser = intent_parser or UserIntentParser()
        self.scorer = scorer or ProductScorer()
        self.reranker = reranker

    def recommend(self, query: str, top_k: int = 5) -> dict:
        """Generate product recommendations for a query."""
        intent = self.intent_parser.parse(query)
        # Forwarded to the retriever's query rewriter (intent-aware step),
        # if one is configured - see src/retrieval/query_rewriter.py.
        intent_hints = {
            "use_case": intent.use_case,
            "priorities": intent.priorities,
        }
        candidates = self.retriever.retrieve(query, top_k=top_k * 3, intent_hints=intent_hints)

        if self.reranker is not None:
            # Cross-encoder prunes and re-orders the candidate pool; keep
            # 2x top_k so multi-criteria scoring still has room to reorder.
            candidates = self.reranker.rerank(query, candidates, top_k=top_k * 2)

        scored_products = []
        for candidate in candidates:
            score_result = self.scorer.score(
                candidate.get("metadata", {}),
                intent,
                self._relevance(candidate),
            )
            scored_products.append(
                {
                    **candidate,
                    "final_score": score_result["total"],
                    "score_breakdown": score_result["breakdown"],
                }
            )

        scored_products.sort(key=lambda x: x["final_score"], reverse=True)
        top_products = scored_products[:top_k]

        return {
            "intent": {
                "use_case": intent.use_case,
                "priorities": intent.priorities,
                "budget": intent.budget,
            },
            "recommendations": top_products,
        }

    @staticmethod
    def _relevance(candidate: dict) -> float:
        """Relevance input for the multi-criteria scorer.

        Prefer the cross-encoder score when present (squashed to [0, 1] with
        a sigmoid, since cross-encoder logits are unbounded); otherwise fall
        back to the retrieval score (cosine-based, already ~[0, 1]).
        """
        rerank_score = candidate.get("rerank_score")
        if rerank_score is not None:
            return 1.0 / (1.0 + math.exp(-rerank_score))
        return candidate.get("score", 0.0)
