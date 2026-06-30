"""Spec Aligner - Căn chỉnh thông số kỹ thuật giữa các sản phẩm để so sánh."""


class SpecAligner:
    """Align specifications across products for comparison."""

    FIELD_ALIASES = {
        "pin": "battery", "dung_luong_pin": "battery", "battery_capacity": "battery",
        "man_hinh": "screen_size", "display": "screen_size", "screen": "screen_size",
        "bo_nho_trong": "storage", "rom": "storage", "internal_storage": "storage",
        "bo_nho_ram": "ram", "memory": "ram",
        "camera_sau": "rear_camera", "main_camera": "rear_camera",
        "camera_truoc": "front_camera", "selfie_camera": "front_camera",
        "chip": "processor", "cpu": "processor", "chipset": "processor",
        "he_dieu_hanh": "os", "operating_system": "os",
        "trong_luong": "weight", "khoi_luong": "weight",
    }

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

        comparison = {"fields": sorted(all_fields), "products": []}
        for prod in normalized_products:
            row = {"name": prod["name"], "product_id": prod["product_id"]}
            for field in comparison["fields"]:
                row[field] = prod["specs"].get(field, "N/A")
            comparison["products"].append(row)

        return comparison
