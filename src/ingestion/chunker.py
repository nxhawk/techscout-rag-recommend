"""
Chunker - Chia sản phẩm thành chunks theo ngữ cảnh (field-based chunking).
"""
from typing import Any


class ProductChunker:
    """Split product profiles into contextual chunks with metadata."""

    def chunk_product(self, product: dict) -> list[dict]:
        """Split a product profile into multiple typed chunks."""
        chunks = []
        base_metadata = {
            "product_id": product["product_id"],
            "brand": product["brand"],
            "category": product["category"],
            "price": product["price"],
        }

        # Chunk 1: General description
        desc_text = f"{product['name']} - {product['brand']}. {product['description']}"
        chunks.append({
            "text": desc_text,
            "chunk_type": "description",
            **base_metadata,
        })

        # Chunk 2: Specifications
        if product.get("specifications"):
            specs_text = self._format_specs(product["name"], product["specifications"])
            chunks.append({
                "text": specs_text,
                "chunk_type": "specifications",
                **base_metadata,
            })

        # Chunk 3: Pros & Cons
        if product.get("pros") or product.get("cons"):
            pros_cons_text = self._format_pros_cons(
                product["name"], product.get("pros", []), product.get("cons", [])
            )
            chunks.append({
                "text": pros_cons_text,
                "chunk_type": "pros_cons",
                **base_metadata,
            })

        # Chunk 4: Review summary
        if product.get("review_summary"):
            review_text = (
                f"Đánh giá về {product['name']}: {product['review_summary']} "
                f"Rating: {product['avg_rating']}/5 ({product['review_count']} reviews)"
            )
            chunks.append({
                "text": review_text,
                "chunk_type": "review",
                **base_metadata,
            })

        return chunks

    def _format_specs(self, name: str, specs: dict[str, Any]) -> str:
        lines = [f"Thông số kỹ thuật {name}:"]
        for key, value in specs.items():
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    def _format_pros_cons(self, name: str, pros: list, cons: list) -> str:
        parts = [f"Đánh giá {name}:"]
        if pros:
            parts.append("Ưu điểm: " + "; ".join(pros))
        if cons:
            parts.append("Nhược điểm: " + "; ".join(cons))
        return "\n".join(parts)
