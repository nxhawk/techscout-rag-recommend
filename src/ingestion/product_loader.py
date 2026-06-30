"""
Product Loader - Đọc dữ liệu sản phẩm từ nhiều nguồn/format.
Hỗ trợ: JSON, CSV, API, crawl data.
"""
import json
import csv
from pathlib import Path
from typing import Optional


class ProductLoader:
    """Load product data from various sources."""

    def __init__(self, data_dir: str = "data/raw/products"):
        self.data_dir = Path(data_dir)

    def load_json(self, filepath: str) -> list[dict]:
        """Load products from JSON file."""
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_csv(self, filepath: str) -> list[dict]:
        """Load products from CSV file."""
        products = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                products.append(dict(row))
        return products

    def load_all(self) -> list[dict]:
        """Load all product files from data directory."""
        all_products = []
        for file in self.data_dir.iterdir():
            if file.suffix == ".json":
                all_products.extend(self.load_json(str(file)))
            elif file.suffix == ".csv":
                all_products.extend(self.load_csv(str(file)))
        return all_products
