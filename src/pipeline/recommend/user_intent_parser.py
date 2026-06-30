"""User Intent Parser - Phân tích ý định người dùng từ câu hỏi."""
from dataclasses import dataclass, field


@dataclass
class UserIntent:
    """Structured representation of user intent."""
    use_case: list[str] = field(default_factory=list)
    budget: dict = field(default_factory=dict)
    priorities: list[str] = field(default_factory=list)
    brand_preference: str | None = None
    category: str | None = None
    target_audience: str | None = None


class UserIntentParser:
    """Parse user queries to extract structured intent."""

    USE_CASE_KEYWORDS = {
        "gaming": ["gaming", "game", "chơi game", "pubg", "liên quân"],
        "photography": ["chụp ảnh", "camera", "quay phim", "selfie"],
        "work": ["công việc", "văn phòng", "office", "làm việc", "excel"],
        "study": ["học", "sinh viên", "học tập", "đọc sách"],
        "entertainment": ["giải trí", "xem phim", "youtube", "tiktok"],
    }

    PRIORITY_KEYWORDS = {
        "battery": ["pin trâu", "pin lâu", "pin khỏe", "dung lượng pin"],
        "display": ["màn đẹp", "màn hình", "display", "amoled", "oled"],
        "performance": ["mạnh", "nhanh", "hiệu năng", "chip", "mượt"],
        "lightweight": ["nhẹ", "mỏng", "gọn", "portable"],
        "camera": ["camera", "chụp ảnh", "quay video"],
        "storage": ["bộ nhớ", "dung lượng", "lưu trữ"],
    }

    def parse(self, query: str) -> UserIntent:
        """Parse a natural language query into structured intent."""
        query_lower = query.lower()
        intent = UserIntent()

        for use_case, keywords in self.USE_CASE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                intent.use_case.append(use_case)

        for priority, keywords in self.PRIORITY_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                intent.priorities.append(priority)

        return intent
