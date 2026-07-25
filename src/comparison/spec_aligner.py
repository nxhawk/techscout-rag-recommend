"""
Spec Aligner - Căn chỉnh thông số kỹ thuật giữa các sản phẩm để so sánh.
"""

from src.constants import SPEC_FIELD_ALIASES


class SpecAligner:
    """Align specifications across products for comparison."""

    FIELD_ALIASES = SPEC_FIELD_ALIASES

    def align_specs(self, products: list[dict]) -> dict:
        """Align specs across multiple products into a comparison table."""
        all_fields = set()
        normalized_products = []

        for product in products:
            specs = product.get("specifications", {})
            normalized = {}
            for key, value in specs.items():
                norm_key = self.FIELD_ALIASES.get(key.lower(), key.lower())
                normalized[norm_key] = value
                all_fields.add(norm_key)
            normalized_products.append({
                "product_id": product["product_id"],
                "name": product["name"],
                "specs": normalized,
            })

        # Build comparison table
        comparison = {"fields": sorted(all_fields), "products": []}
        for prod in normalized_products:
            row = {"name": prod["name"], "product_id": prod["product_id"]}
            for field in comparison["fields"]:
                row[field] = prod["specs"].get(field, "N/A")
            comparison["products"].append(row)

        return comparison
