"""Comparator - So sánh N sản phẩm theo từng tiêu chí."""
from src.pipeline.compare.spec_aligner import SpecAligner


class ProductComparator:
    """Compare multiple products across specifications."""

    def __init__(self, spec_aligner: SpecAligner | None = None):
        self.spec_aligner = spec_aligner or SpecAligner()

    def compare(self, products: list[dict]) -> dict:
        """Compare products and determine winners per criterion."""
        aligned = self.spec_aligner.align_specs(products)

        comparison_result = {
            "products": [p["name"] for p in products],
            "comparison_table": aligned,
            "highlights": self._find_highlights(products),
            "price_comparison": self._compare_prices(products),
            "rating_comparison": self._compare_ratings(products),
        }
        return comparison_result

    def _find_highlights(self, products: list[dict]) -> list[dict]:
        """Find standout features for each product."""
        highlights = []
        for product in products:
            highlights.append({
                "name": product["name"],
                "best_at": [],
                "worst_at": [],
            })
        return highlights

    def _compare_prices(self, products: list[dict]) -> dict:
        prices = [(p["name"], p.get("price", 0)) for p in products]
        prices.sort(key=lambda x: x[1])
        return {
            "cheapest": prices[0] if prices else None,
            "most_expensive": prices[-1] if prices else None,
            "all": prices,
        }

    def _compare_ratings(self, products: list[dict]) -> dict:
        ratings = [(p["name"], p.get("avg_rating", 0)) for p in products]
        ratings.sort(key=lambda x: x[1], reverse=True)
        return {
            "highest_rated": ratings[0] if ratings else None,
            "all": ratings,
        }
