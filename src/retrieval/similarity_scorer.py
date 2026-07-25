"""
Similarity Scorer - Tính điểm tương đồng tổng hợp.
"""
import math

from src.constants import MAX_RATING, POPULARITY_LOG_BASE, SIMILARITY_SCORE_WEIGHTS


class SimilarityScorer:
    """Calculate composite similarity scores."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or dict(SIMILARITY_SCORE_WEIGHTS)

    def compute_score(
        self,
        semantic_score: float,
        product: dict,
        filters: dict,
    ) -> float:
        """Compute weighted composite score."""
        scores = {
            "semantic": semantic_score,
            "price_match": self._price_match_score(product.get("price", 0), filters),
            "rating": self._rating_score(product.get("avg_rating", 0)),
            "popularity": self._popularity_score(product.get("review_count", 0)),
        }
        total = sum(scores[k] * self.weights[k] for k in self.weights)
        return round(total, 4)

    def _price_match_score(self, price: int, filters: dict) -> float:
        target = filters.get("price_max", filters.get("price_min"))
        if not target or not price:
            return 0.5
        ratio = min(price, target) / max(price, target)
        return ratio

    def _rating_score(self, rating: float) -> float:
        return min(rating / MAX_RATING, 1.0)

    def _popularity_score(self, review_count: int) -> float:
        return min(math.log(review_count + 1) / math.log(POPULARITY_LOG_BASE), 1.0)
