"""Pros/Cons Extractor - Trích xuất ưu/nhược điểm từ review và specs."""


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
        specs = product.get("specifications", {})
        price = product.get("price", 0)

        if price and price < 8_000_000:
            best_for.append("Sinh viên / Ngân sách hạn chế")
        elif price and price > 25_000_000:
            best_for.append("Người dùng cao cấp")

        return best_for
