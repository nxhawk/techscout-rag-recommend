# crawl.py — Luồng chạy

Crawl dữ liệu sản phẩm từ các nguồn đã cấu hình (thegioididong, cellphones) vào
`data/raw/crawled/`.

```bash
uv run python scripts/crawl.py --source tgdd
uv run python scripts/crawl.py --source cellphones --category smartphone
uv run python scripts/crawl.py --all
```

## Sơ đồ luồng

```mermaid
flowchart TB
    MAIN["main()<br/><i>scripts/crawl.py</i>"] --> ARGS["parse_args()<br/><i>scripts/crawl.py</i>"]
    MAIN --> CFG["CrawlerConfig.from_yaml()<br/><i>src/crawler/config.py</i>"]
    YAML[("configs/crawler.yaml")] --> CFG
    MAIN -->|"với mỗi nguồn được bật"| RUN["run_source()<br/><i>scripts/crawl.py</i>"]

    RUN --> REG["SPIDER_REGISTRY[name]<br/><i>src/crawler/spiders/__init__.py</i>"]
    REG --> SPIDER["TgddSpider / CellphonesSpider<br/><i>src/crawler/spiders/*_spider.py</i>"]
    RUN --> PIPE["CrawlPipeline(config)<br/><i>src/crawler/pipeline.py</i>"]
    RUN --> PRUN["pipeline.run(spider, categories)<br/><i>src/crawler/pipeline.py</i>"]

    PRUN --> GS["config.get_source(name)<br/><i>src/crawler/config.py</i>"]
    PRUN --> HTTP["HttpClient(config)<br/><i>src/crawler/http_client.py</i>"]
    HTTP --> RL["RateLimiter<br/><i>src/crawler/rate_limiter.py</i>"]
    HTTP --> ROB["RobotsChecker<br/><i>src/crawler/robots.py</i>"]
    PRUN --> BIND["spider.bind(client, source_cfg)<br/><i>src/crawler/spiders/base_spider.py</i>"]

    PRUN -->|"với mỗi category"| DISC["spider.discover(category)<br/><i>src/crawler/spiders/base_spider.py</i>"]
    DISC --> BLU["build_list_url()"]
    DISC --> GET["client.get(url)<br/><i>src/crawler/http_client.py</i>"]
    DISC --> PL["parse_list(html)<br/><i>src/crawler/spiders/*_spider.py</i>"]

    PRUN --> CD["spider.crawl_details(urls)<br/><i>src/crawler/spiders/base_spider.py</i>"]
    CD --> GM["client.get_many(urls)<br/><i>src/crawler/http_client.py</i>"]
    CD --> PD["parse_detail(html, url)<br/><i>src/crawler/spiders/*_spider.py</i>"]
    PD --> MODEL["CrawledProduct<br/><i>src/crawler/models.py</i>"]
    CD --> CR["collect_reviews(product, html)<br/><i>src/crawler/spiders/base_spider.py</i>"]

    PRUN --> SAVE["storage.save(result)<br/><i>src/crawler/storage.py</i>"]
    SAVE --> OUT[("data/raw/crawled/&lt;source&gt;/&lt;timestamp&gt;.json<br/>data/raw/crawled/&lt;source&gt;/latest.json")]
```

## Từng bước

| # | Bước | Function | File |
|---|------|----------|------|
| 1 | Parse tham số CLI (`--source`, `--category`, `--all`, `--config`) | `parse_args()` | `scripts/crawl.py` |
| 2 | Load config crawler từ YAML | `CrawlerConfig.from_yaml()` | `src/crawler/config.py` |
| 3 | Xác định target: một nguồn, hoặc tất cả nguồn được bật | `main()` | `scripts/crawl.py` |
| 4 | Tra cứu spider class cho nguồn | `SPIDER_REGISTRY[name]` | `src/crawler/spiders/__init__.py` |
| 5 | Khởi tạo pipeline và chạy | `CrawlPipeline.run()` | `src/crawler/pipeline.py` |
| 6 | Mở HTTP client (retry + rate limit + robots.txt) | `HttpClient` | `src/crawler/http_client.py` |
| 7 | Tìm URL sản phẩm theo category (trang danh sách, phân trang) | `BaseSpider.discover()` | `src/crawler/spiders/base_spider.py` |
| 8 | Fetch trang chi tiết đồng thời và parse sản phẩm | `BaseSpider.crawl_details()` → `parse_detail()` | `src/crawler/spiders/base_spider.py`, `*_spider.py` |
| 9 | Thu thập review cho mỗi sản phẩm (hook tùy chọn) | `BaseSpider.collect_reviews()` | `src/crawler/spiders/base_spider.py` |
| 10 | Lưu bản chạy có timestamp + snapshot `latest.json` | `CrawlStorage.save()` | `src/crawler/storage.py` |

## Kết quả

Mỗi lần chạy ghi hai file cho mỗi nguồn trong `data/raw/crawled/<source>/`:
file `YYYYMMDD_HHMMSS.json` (toàn bộ `CrawlResult`, gồm cả lỗi) và
`latest.json` (chỉ sản phẩm) — file mà `scripts/ingest.py` đọc mặc định.
