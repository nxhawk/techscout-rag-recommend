"""
Price Tracker - Theo dõi và cập nhật giá sản phẩm.
"""
import json
from datetime import datetime
from pathlib import Path


class PriceTracker:
    """Track and update product prices."""

    def __init__(self, price_dir: str = "data/raw/pricing"):
        self.price_dir = Path(price_dir)
        self.price_dir.mkdir(parents=True, exist_ok=True)

    def update_price(self, product_id: str, price: int, source: str) -> None:
        """Record a new price point for a product."""
        history_file = self.price_dir / f"{product_id}_prices.json"
        history = self._load_history(history_file)
        history.append({
            "price": price,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        })
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_latest_price(self, product_id: str) -> int | None:
        """Get the most recent price for a product."""
        history_file = self.price_dir / f"{product_id}_prices.json"
        history = self._load_history(history_file)
        return history[-1]["price"] if history else None

    def _load_history(self, filepath: Path) -> list[dict]:
        if filepath.exists():
            with open(filepath, "r") as f:
                return json.load(f)
        return []
