# Đóng góp

## Thiết lập môi trường phát triển

```bash
git clone https://github.com/nxhawk/rag-product-recommend.git
cd rag-product-recommend
uv sync --group dev --group docs
```

## Quy tắc Code Style

- **Ngôn ngữ**: Toàn bộ code, comment, docstring, và tài liệu phải bằng tiếng Anh.
- **Văn bản hiển thị cho người dùng** (prompt, API response): Tiếng Việt.
- **Type hint**: Bắt buộc trên mọi function signature.
- **Version Python**: Dùng các tính năng của 3.11+ (`X | Y` union, `match` statement).
- **Import**: Luôn dùng đường dẫn tuyệt đối từ root dự án (`from src.retrieval.filter_engine import FilterEngine`).
- **Quản lý package**: Chỉ dùng `uv`. Thêm dependency bằng `uv add <package>`.

## Thêm một Module mới

1. Tạo file module trong thư mục con `src/` phù hợp.
2. Dùng import tuyệt đối.
3. Thêm type hint cho mọi hàm public.
4. Viết docstring bằng tiếng Anh.
5. Thêm unit test trong `tests/unit/<domain>/test_<module>.py`, mirror đường dẫn module dưới `src/` hoặc `api/` (xem [Testing](testing.vi.md)).
6. Cập nhật `CLAUDE.md` nếu module đưa ra pattern mới.

## Commit Message

Dùng [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add cross-encoder reranking
fix: handle empty query in filter engine
docs: update API endpoint documentation
test: add integration tests for compare pipeline
```

## Chạy Docs cục bộ

```bash
uv run mkdocs serve
```

Docs sẽ có sẵn tại `http://localhost:8000`.
