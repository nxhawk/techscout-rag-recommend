"""
Filter Engine - Trích xuất điều kiện lọc từ câu hỏi tự nhiên.
"""
import re
from typing import Any


class FilterEngine:
    """Extract filter conditions from natural language queries."""

    BRAND_KEYWORDS = [
        "apple", "samsung", "xiaomi", "oppo", "vivo", "realme",
        "huawei", "sony", "lg", "asus", "dell", "hp", "lenovo",
    ]

    CATEGORY_MAP = {
        "điện thoại": "smartphone", "phone": "smartphone",
        "laptop": "laptop", "máy tính xách tay": "laptop",
        "tai nghe": "headphone", "earbuds": "headphone",
        "máy tính bảng": "tablet", "tablet": "tablet",
    }

    def extract_filters(self, query: str) -> dict[str, Any]:
        """Extract all applicable filters from a query."""
        query_lower = query.lower()
        filters = {}

        price = self._extract_price(query_lower)
        if price:
            filters.update(price)

        brand = self._extract_brand(query_lower)
        if brand:
            filters["brand"] = brand

        category = self._extract_category(query_lower)
        if category:
            filters["category"] = category

        rating = self._extract_rating(query_lower)
        if rating:
            filters["min_rating"] = rating

        return filters

    def _extract_price(self, query: str) -> dict | None:
        patterns = [
            (r"tầm\s+(\d+)\s*triệu", lambda m: {"price_min": int(m.group(1)) * 800_000, "price_max": int(m.group(1)) * 1_200_000}),
            (r"dưới\s+(\d+)\s*triệu", lambda m: {"price_max": int(m.group(1)) * 1_000_000}),
            (r"trên\s+(\d+)\s*triệu", lambda m: {"price_min": int(m.group(1)) * 1_000_000}),
            (r"từ\s+(\d+)\s*đến\s+(\d+)\s*triệu", lambda m: {"price_min": int(m.group(1)) * 1_000_000, "price_max": int(m.group(2)) * 1_000_000}),
        ]
        for pattern, extractor in patterns:
            match = re.search(pattern, query)
            if match:
                return extractor(match)
        return None

    def _extract_brand(self, query: str) -> str | None:
        for brand in self.BRAND_KEYWORDS:
            if brand in query:
                return brand.capitalize()
        return None

    def _extract_category(self, query: str) -> str | None:
        for keyword, category in self.CATEGORY_MAP.items():
            if keyword in query:
                return category
        return None

    def _extract_rating(self, query: str) -> float | None:
        if any(kw in query for kw in ["đánh giá tốt", "rating cao", "được đánh giá cao"]):
            return 4.0
        return None
