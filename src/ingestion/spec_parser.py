"""
Spec Parser - Parse và chuẩn hóa thông số kỹ thuật sản phẩm.
"""
import re
from typing import Any

from src.constants import SPEC_FIELD_ALIASES

# SpecParser historically normalizes only this narrow subset of keys, unlike
# SpecAligner (src/comparison/spec_aligner.py / src/pipeline/compare/spec_aligner.py)
# which normalizes the full canonical SPEC_FIELD_ALIASES set. Keep behavior
# unchanged by picking a documented subset here rather than adopting the
# full canonical dict wholesale (which would additionally start normalizing
# keys like "display"/"rom" that this parser previously left untouched).
# "bo_nho" -> "storage" is an extra alias not present in the shared
# SPEC_FIELD_ALIASES dict (SpecAligner uses "bo_nho_trong" instead), so it is
# kept as a local addition here to preserve this parser's exact behavior.
_KEY_MAP: dict[str, str] = {
    key: SPEC_FIELD_ALIASES[key]
    for key in ("pin", "dung_luong_pin", "man_hinh", "camera_sau")
}
_KEY_MAP["bo_nho"] = "storage"


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
        return _KEY_MAP.get(key, key)

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
