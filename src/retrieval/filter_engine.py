"""
Filter Engine - Trích xuất điều kiện lọc từ câu hỏi tự nhiên.
"""
import re
from typing import Any, ClassVar

from src.constants import (
    GOOD_RATING_THRESHOLD,
    PRICE_BAND_LOWER_FACTOR,
    PRICE_BAND_UPPER_FACTOR,
    Category,
)


class FilterEngine:
    """Extract filter conditions from natural language queries."""

    BRAND_KEYWORDS: ClassVar[list[str]] = [
        "apple", "samsung", "xiaomi", "oppo", "vivo", "realme",
        "huawei", "sony", "lg", "asus", "dell", "hp", "lenovo",
    ]

    CATEGORY_MAP: ClassVar[dict[str, str]] = {
        "điện thoại": Category.SMARTPHONE.value, "phone": Category.SMARTPHONE.value,
        "laptop": Category.LAPTOP.value, "máy tính xách tay": Category.LAPTOP.value,
        "tai nghe": Category.HEADPHONE.value, "earbuds": Category.HEADPHONE.value,
        "máy tính bảng": Category.TABLET.value, "tablet": Category.TABLET.value,
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
            # Vietnamese: "tầm/dưới/trên/từ X đến Y triệu"
            (r"tầm\s+(\d+)\s*triệu", lambda m: {"price_min": int(int(m.group(1)) * 1_000_000 * PRICE_BAND_LOWER_FACTOR), "price_max": int(int(m.group(1)) * 1_000_000 * PRICE_BAND_UPPER_FACTOR)}),
            (r"dưới\s+(\d+)\s*triệu", lambda m: {"price_max": int(m.group(1)) * 1_000_000}),
            (r"trên\s+(\d+)\s*triệu", lambda m: {"price_min": int(m.group(1)) * 1_000_000}),
            (r"từ\s+(\d+)\s*đến\s+(\d+)\s*triệu", lambda m: {"price_min": int(m.group(1)) * 1_000_000, "price_max": int(m.group(2)) * 1_000_000}),
            # English: "under/below/over/above X million", "from X to Y million",
            # "around X million" (assumes VND millions, same as Vietnamese "triệu")
            (r"(?:under|below|less than)\s+(\d+)\s*(?:million|mil|tr)\b", lambda m: {"price_max": int(m.group(1)) * 1_000_000}),
            (r"(?:over|above|more than)\s+(\d+)\s*(?:million|mil|tr)\b", lambda m: {"price_min": int(m.group(1)) * 1_000_000}),
            (r"from\s+(\d+)\s*to\s+(\d+)\s*(?:million|mil|tr)\b", lambda m: {"price_min": int(m.group(1)) * 1_000_000, "price_max": int(m.group(2)) * 1_000_000}),
            (r"around\s+(\d+)\s*(?:million|mil|tr)\b", lambda m: {"price_min": int(int(m.group(1)) * 1_000_000 * PRICE_BAND_LOWER_FACTOR), "price_max": int(int(m.group(1)) * 1_000_000 * PRICE_BAND_UPPER_FACTOR)}),
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
            return GOOD_RATING_THRESHOLD
        return None
