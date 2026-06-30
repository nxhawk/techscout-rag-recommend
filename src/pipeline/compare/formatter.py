"""Comparison Formatter - Format kết quả so sánh thành output đẹp."""


class ComparisonFormatter:
    """Format comparison results for output."""

    def format_markdown_table(self, comparison: dict) -> str:
        """Format comparison as markdown table."""
        products = comparison.get("comparison_table", {}).get("products", [])
        fields = comparison.get("comparison_table", {}).get("fields", [])

        if not products or not fields:
            return "Không có dữ liệu để so sánh."

        header = "| Thông số | " + " | ".join(p["name"] for p in products) + " |"
        separator = "|" + "|".join(["---"] * (len(products) + 1)) + "|"

        rows = [header, separator]
        for field in fields:
            row = f"| {field} | " + " | ".join(str(p.get(field, "N/A")) for p in products) + " |"
            rows.append(row)

        rows.append(
            "| Giá | "
            + " | ".join(f"{p.get('price', 'N/A'):,} VND" if isinstance(p.get('price'), int) else "N/A" for p in products)
            + " |"
        )

        return "\n".join(rows)

    def format_summary(self, comparison: dict) -> str:
        """Format a human-readable summary of comparison."""
        lines = ["## Tóm tắt so sánh\n"]
        price_info = comparison.get("price_comparison", {})
        if price_info.get("cheapest"):
            name, price = price_info["cheapest"]
            lines.append(f"- Giá tốt nhất: **{name}** ({price:,} VND)")
        rating_info = comparison.get("rating_comparison", {})
        if rating_info.get("highest_rated"):
            name, rating = rating_info["highest_rated"]
            lines.append(f"- Đánh giá cao nhất: **{name}** ({rating}/5)")
        return "\n".join(lines)
