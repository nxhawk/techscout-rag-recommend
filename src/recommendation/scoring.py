"""
Scoring - Chấm điểm sản phẩm dựa trên nhiều tiêu chí.
"""
import math

from src.constants import (
    BUDGET_MISMATCH_PENALTY,
    FEW_REVIEWS_PENALTY,
    FEW_REVIEWS_THRESHOLD,
    MAX_RATING,
    POPULARITY_LOG_BASE,
    RECOMMEND_SCORE_WEIGHTS,
)
from src.recommendation.user_intent_parser import UserIntent


class ProductScorer:
    """Score products based on multiple criteria."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or dict(RECOMMEND_SCORE_WEIGHTS)

    def score(self, product: dict, intent: UserIntent, retrieval_score: float) -> dict:
        """Calculate composite score for a product."""
        scores = {
            "relevance": retrieval_score,
            "review": self._review_score(product),
            "value": self._value_score(product, intent),
            "popularity": self._popularity_score(product),
        }
        total = sum(scores[k] * self.weights[k] for k in self.weights)
        return {"total": round(total, 4), "breakdown": scores}

    def _review_score(self, product: dict) -> float:
        rating = product.get("avg_rating", 0)
        count = product.get("review_count", 0)
        if count < FEW_REVIEWS_THRESHOLD:
            return rating / MAX_RATING * FEW_REVIEWS_PENALTY  # Penalty for few reviews
        return rating / MAX_RATING

    def _value_score(self, product: dict, intent: UserIntent) -> float:
        price = product.get("price", 0)
        budget_max = intent.budget.get("price_max")
        if not budget_max or not price:
            return 0.5
        if price <= budget_max:
            return 1.0 - (budget_max - price) / budget_max * BUDGET_MISMATCH_PENALTY
        return max(0, 1.0 - (price - budget_max) / budget_max)

    def _popularity_score(self, product: dict) -> float:
        count = product.get("review_count", 0)
        return min(math.log(count + 1) / math.log(POPULARITY_LOG_BASE), 1.0)
