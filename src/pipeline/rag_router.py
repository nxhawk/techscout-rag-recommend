"""
RAG Router - Phân loại câu hỏi và route đến pipeline phù hợp.
"""
import re
from enum import Enum


class QueryType(Enum):
    RECOMMEND = "recommend"
    COMPARE = "compare"
    INFO = "info"
    HYBRID = "hybrid"


class RAGRouter:
    """Route queries to the appropriate pipeline."""

    RECOMMEND_PATTERNS = [
        r"gợi ý", r"nên mua", r"tư vấn", r"recommend",
        r"muốn mua", r"tìm .* phù hợp", r"cho tôi .* tốt",
        r"suggest", r"đề xuất",
    ]

    COMPARE_PATTERNS = [
        r"so sánh", r"compare", r"hay\b", r"vs\.?",
        r"khác nhau", r"tốt hơn", r"nào hơn",
        r"chọn .* hay", r"giữa .* và",
    ]

    INFO_PATTERNS = [
        r"thông số", r"giá", r"specs", r"cấu hình",
        r"bao nhiêu", r"chi tiết", r"review",
    ]

    def route(self, query: str) -> QueryType:
        """Classify query and determine the appropriate pipeline."""
        query_lower = query.lower()

        is_recommend = any(re.search(p, query_lower) for p in self.RECOMMEND_PATTERNS)
        is_compare = any(re.search(p, query_lower) for p in self.COMPARE_PATTERNS)
        is_info = any(re.search(p, query_lower) for p in self.INFO_PATTERNS)

        if is_recommend and is_compare:
            return QueryType.HYBRID
        if is_compare:
            return QueryType.COMPARE
        if is_recommend:
            return QueryType.RECOMMEND
        if is_info:
            return QueryType.INFO

        # Default to recommend
        return QueryType.RECOMMEND
