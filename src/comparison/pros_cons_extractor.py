"""
Pros/Cons Extractor - Trích xuất ưu/nhược điểm từ review và specs.
"""

from src.constants import BUDGET_TIER_MAX_PRICE, PREMIUM_TIER_MIN_PRICE


class ProsConsExtractor:
    """Extract pros and cons from reviews and specifications."""

    def extract(self, product: dict) -> dict:
        """Extract pros and cons for a product."""
        return {
            "product_id": product.get("product_id"),
            "name": product.get("name"),
            "pros": product.get("pros", []),
            "cons": product.get("cons", []),
            "best_for": self._determine_best_for(product),
        }

    def _determine_best_for(self, product: dict) -> list[str]:
        """Determine which user profiles this product is best for."""
        best_for = []
        price = product.get("price", 0)

        # Simple heuristic rules — will be enhanced by LLM
        if price and price < BUDGET_TIER_MAX_PRICE:
            best_for.append("Sinh viên / Ngân sách hạn chế")
        elif price and price > PREMIUM_TIER_MIN_PRICE:
            best_for.append("Người dùng cao cấp")

        return best_for
