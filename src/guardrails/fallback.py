"""Deterministic fallback responses - no LLM call.

Used when the LLM output fails schema validation or grounding removes every
item. The fallback is built purely from already-retrieved candidates so the
API always returns something schema-valid instead of erroring out.
"""

from typing import Any

_NO_LLM_REASON = "He thong tam thoi khong tao duoc mo ta chi tiet; day la ket qua xep hang tu dong."


def _metadata(product: dict[str, Any]) -> dict[str, Any]:
    metadata = product.get("metadata")
    return metadata if isinstance(metadata, dict) else product


def build_recommend_fallback(
    retrieved_products: list[dict[str, Any]], top_k: int
) -> dict[str, Any]:
    """Build a ``RecommendLLMOutput``-shaped dict straight from retrieval scores."""
    items = []
    for product in retrieved_products[: max(top_k, 0)]:
        meta = _metadata(product)
        items.append(
            {
                "name": meta.get("name", "N/A"),
                "price": meta.get("price"),
                "reason": _NO_LLM_REASON,
                "pros": [],
                "cons": [],
                "best_for": "",
            }
        )
    summary = (
        "Khong the tao mo ta chi tiet luc nay. Duoi day la danh sach san pham phu hop nhat "
        "theo diem xep hang cua he thong."
        if items
        else "Khong tim thay san pham phu hop voi yeu cau cua ban. Vui long thu lai voi mo ta khac."
    )
    return {"recommendations": items, "summary": summary}


def build_compare_fallback(
    products: list[dict[str, Any]], comparison_table: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a ``CompareLLMOutput``-shaped dict from the raw comparison table."""
    analysis = [
        {"name": p.get("name", "N/A"), "pros": [], "cons": [], "best_for": ""} for p in products
    ]
    conclusion = (
        "Khong the tao phan tich chi tiet luc nay. Vui long tham khao bang so sanh thong so o tren."
        if products
        else "Khong du du lieu de so sanh."
    )
    return {
        "criteria_comparison": [],
        "product_analysis": analysis,
        "conclusion": conclusion,
    }
