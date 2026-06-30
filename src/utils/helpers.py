"""Helpers - Các hàm tiện ích chung."""
import json
from pathlib import Path
from typing import Any


def load_json(filepath: str) -> Any:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, filepath: str) -> None:
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_price(price: int, currency: str = "VND") -> str:
    return f"{price:,} {currency}"
