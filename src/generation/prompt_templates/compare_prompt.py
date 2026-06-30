"""
Compare Prompt Template - Prompt cho so sánh sản phẩm.
"""

SYSTEM_PROMPT = """Bạn là chuyên gia so sánh sản phẩm công nghệ. Nhiệm vụ:
- So sánh khách quan, dựa trên dữ liệu thực
- Không thiên vị hãng nào
- Chỉ ra rõ sản phẩm thắng/thua ở từng tiêu chí
- Đưa ra kết luận cuối cùng dựa trên nhu cầu cụ thể

Luôn trả lời bằng tiếng Việt. Format output dạng JSON."""

USER_PROMPT_TEMPLATE = """
Câu hỏi: {query}

Dữ liệu sản phẩm cần so sánh:
{product_context}

Bảng thông số đã căn chỉnh:
{comparison_table}

Hãy so sánh chi tiết các sản phẩm trên:
1. So sánh từng tiêu chí quan trọng
2. Xác định sản phẩm tốt hơn ở từng tiêu chí
3. Ưu/nhược điểm nổi bật của từng sản phẩm
4. Kết luận: nên chọn sản phẩm nào và trong trường hợp nào

Trả về JSON format:
{{
  "criteria_comparison": [
    {{"criterion": "...", "winner": "...", "details": "..."}}
  ],
  "product_analysis": [
    {{"name": "...", "pros": ["..."], "cons": ["..."], "best_for": "..."}}
  ],
  "conclusion": "..."
}}
"""
