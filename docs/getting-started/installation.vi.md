# Cài đặt

## Yêu cầu

- Python 3.11+
- Trình quản lý gói [uv](https://docs.astral.sh/uv/)
- Một Gemini API key (provider mặc định cho cả LLM và embedding). Key Anthropic và/hoặc OpenAI là tùy chọn — chỉ cần khi bạn đổi provider trong `configs/settings.yaml`.
- Docker + Docker Compose (khuyến nghị) — toàn bộ stack phụ trợ (Postgres/pgvector, Elasticsearch, Kafka, Debezium Connect, Redis) được cung cấp qua `docker/docker-compose.yml`, nên bạn không cần cài các service này thủ công.

## Cài đặt uv

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS / Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

## Clone và cài đặt

```bash
git clone https://github.com/nxhawk/rag-product-recommend.git
cd rag-product-recommend
uv sync
```

Lệnh này cài đặt toàn bộ dependencies từ `pyproject.toml` và tự động tạo virtual environment (tương tự `npm install`).

## Biến môi trường

Tạo một file `.env` ở thư mục gốc của dự án và thêm (các) API key của bạn. Repo không đi kèm `.env.example`, nên hãy tự tạo file này:

```bash
# tạo file .env (repo không đi kèm .env.example)
touch .env
```

Mặc định dự án dùng Gemini cho cả LLM và embedding, nên `GEMINI_API_KEY` là key duy nhất bạn cần. Các key còn lại là tùy chọn và chỉ cần khi bạn đổi provider. Các biến override hạ tầng đều có giá trị mặc định hợp lý (và được Docker Compose thiết lập tự động).

| Biến                      | Bắt buộc | Mô tả                                                                                        |
| ------------------------- | -------- | -------------------------------------------------------------------------------------------- |
| `GEMINI_API_KEY`          | Có*      | Key Google Gemini — dùng cho provider LLM và embedding mặc định                              |
| `ANTHROPIC_API_KEY`       | Không    | Key Anthropic Claude — chỉ khi bạn đặt `llm_provider: anthropic`                             |
| `OPENAI_API_KEY`          | Không    | Key OpenAI — chỉ khi bạn đổi provider LLM hoặc embedding sang OpenAI                         |
| `DATABASE_URL`            | Không    | Chuỗi kết nối Postgres (mặc định `postgresql://postgres:postgres@localhost:5432/rag_products`) |
| `ELASTICSEARCH_URL`       | Không    | URL Elasticsearch cho index keyword (mặc định `http://localhost:9200`)                       |
| `KAFKA_BOOTSTRAP_SERVERS` | Không    | Địa chỉ Kafka bootstrap cho CDC (mặc định `localhost:9092`)                                  |
| `KEYWORD_BACKEND`         | Không    | `elasticsearch` (mặc định) hoặc `memory` cho fallback BM25 in-memory                          |

*Tối thiểu bạn cần key cho provider đã cấu hình. Với config mặc định thì đó là `GEMINI_API_KEY`.

## Cài đặt dependencies cho Dev

```bash
uv sync --group dev
```

## Cài đặt dependencies cho Docs

```bash
uv sync --group docs
```
