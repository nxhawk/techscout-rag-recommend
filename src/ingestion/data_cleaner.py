"""
Data Cleaner - Làm sạch và chuẩn hóa dữ liệu sản phẩm.
"""
import re
from typing import Any


class DataCleaner:
    """Clean and normalize product data."""

    def clean_text(self, text: str) -> str:
        """Remove HTML tags, extra whitespace, special characters."""
        text = re.sub(r"<[^>]+>", "", text)  # Remove HTML
        text = re.sub(r"\s+", " ", text)     # Collapse whitespace
        text = text.strip()
        return text

    def normalize_price(self, price: Any, currency: str = "VND") -> int:
        """Normalize price to integer."""
        if isinstance(price, str):
            price = re.sub(r"[^\d]", "", price)
        return int(price) if price else 0

    def build_product_profile(self, raw_product: dict) -> dict:
        """Build standardized product profile from raw data."""
        return {
            "product_id": raw_product.get("id", ""),
            "name": self.clean_text(raw_product.get("name", "")),
            "brand": raw_product.get("brand", "").strip(),
            "category": raw_product.get("category", "").lower(),
            "price": self.normalize_price(raw_product.get("price", 0)),
            "currency": raw_product.get("currency", "VND"),
            "specifications": raw_product.get("specifications", {}),
            "description": self.clean_text(raw_product.get("description", "")),
            "pros": raw_product.get("pros", []),
            "cons": raw_product.get("cons", []),
            "avg_rating": float(raw_product.get("avg_rating", 0)),
            "review_count": int(raw_product.get("review_count", 0)),
            "review_summary": "",
            "tags": raw_product.get("tags", []),
            "updated_at": raw_product.get("updated_at", ""),
        }
