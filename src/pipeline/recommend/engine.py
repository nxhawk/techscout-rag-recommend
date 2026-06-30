"""Recommend Engine - Logic gợi ý sản phẩm chính."""
from src.pipeline.recommend.user_intent_parser import UserIntentParser, UserIntent
from src.pipeline.recommend.scoring import ProductScorer
from src.retrieval.product_retriever import ProductRetriever


class RecommendEngine:
    """Main recommendation engine."""

    def __init__(
        self,
        retriever: ProductRetriever,
        intent_parser: UserIntentParser | None = None,
        scorer: ProductScorer | None = None,
    ):
        self.retriever = retriever
        self.intent_parser = intent_parser or UserIntentParser()
        self.scorer = scorer or ProductScorer()

    def recommend(self, query: str, top_k: int = 5) -> dict:
        """Generate product recommendations for a query."""
        intent = self.intent_parser.parse(query)
        candidates = self.retriever.retrieve(query, top_k=top_k * 3)

        scored_products = []
        for candidate in candidates:
            score_result = self.scorer.score(
                candidate.get("metadata", {}),
                intent,
                candidate.get("score", 0),
            )
            scored_products.append({
                **candidate,
                "final_score": score_result["total"],
                "score_breakdown": score_result["breakdown"],
            })

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
