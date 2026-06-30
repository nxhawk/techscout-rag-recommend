"""
Review Loader - Đọc và parse review người dùng.
"""
import json
from pathlib import Path


class ReviewLoader:
    """Load and parse user reviews."""

    def __init__(self, data_dir: str = "data/raw/reviews"):
        self.data_dir = Path(data_dir)

    def load_reviews(self, product_id: str) -> list[dict]:
        """Load reviews for a specific product."""
        filepath = self.data_dir / f"{product_id}_reviews.json"
        if not filepath.exists():
            return []
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_all_reviews(self) -> dict[str, list[dict]]:
        """Load all reviews grouped by product_id."""
        all_reviews = {}
        for file in self.data_dir.glob("*_reviews.json"):
            product_id = file.stem.replace("_reviews", "")
            all_reviews[product_id] = self.load_reviews(product_id)
        return all_reviews
