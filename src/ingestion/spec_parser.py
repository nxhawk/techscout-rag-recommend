"""
Spec Parser - Parse và chuẩn hóa thông số kỹ thuật sản phẩm.
"""
import re
from typing import Any


class SpecParser:
    """Parse and normalize product specifications."""

    UNIT_MAP = {
        "gb": "GB", "tb": "TB", "mb": "MB",
        "mah": "mAh", "inch": "inch", "\"": "inch",
        "mp": "MP", "hz": "Hz", "ghz": "GHz",
        "kg": "kg", "g": "g",
    }

    def parse_specs(self, raw_specs: dict[str, Any]) -> dict[str, Any]:
        """Parse and normalize raw specifications."""
        normalized = {}
        for key, value in raw_specs.items():
            norm_key = self._normalize_key(key)
            norm_value = self._normalize_value(value)
            normalized[norm_key] = norm_value
        return normalized

    def _normalize_key(self, key: str) -> str:
        """Normalize spec key names."""
        key = key.lower().strip().replace(" ", "_")
        key_map = {
            "pin": "battery", "dung_luong_pin": "battery",
            "man_hinh": "screen_size", "bo_nho": "storage",
            "ram": "ram", "camera_sau": "rear_camera",
        }
        return key_map.get(key, key)

    def _normalize_value(self, value: Any) -> Any:
        """Normalize spec values with units."""
        if isinstance(value, str):
            for unit_lower, unit_standard in self.UNIT_MAP.items():
                value = re.sub(
                    rf"(\d+)\s*{unit_lower}",
                    rf"\1 {unit_standard}",
                    value,
                    flags=re.IGNORECASE,
                )
        return value
