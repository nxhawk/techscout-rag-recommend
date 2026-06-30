"""
Multi-Field Embedder - Tạo embeddings riêng theo từng field của sản phẩm.
"""
from .product_embedder import ProductEmbedder


class MultiFieldEmbedder:
    """Generate separate embeddings for different product fields."""

    def __init__(self, embedder: ProductEmbedder):
        self.embedder = embedder

    def embed_product_fields(self, product: dict) -> dict[str, list[float]]:
        """Create separate embeddings for each product field."""
        field_texts = {
            "description": f"{product['name']} {product.get('description', '')}",
            "specifications": self._specs_to_text(product.get("specifications", {})),
            "reviews": product.get("review_summary", ""),
        }
        return {
            field: self.embedder.embed_text(text)
            for field, text in field_texts.items()
            if text.strip()
        }

    def _specs_to_text(self, specs: dict) -> str:
        parts = []
        for k, v in specs.items():
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            parts.append(f"{k}: {v}")
        return "; ".join(parts)
