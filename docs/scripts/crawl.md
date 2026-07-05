# crawl.py — Execution Flow

Crawls product data from configured sources (thegioididong, cellphones) into
`data/raw/crawled/`.

```bash
uv run python scripts/crawl.py --source tgdd
uv run python scripts/crawl.py --source cellphones --category smartphone
uv run python scripts/crawl.py --all
```

## Flow diagram

```mermaid
flowchart TB
    MAIN["main()<br/><i>scripts/crawl.py</i>"] --> ARGS["parse_args()<br/><i>scripts/crawl.py</i>"]
    MAIN --> CFG["CrawlerConfig.from_yaml()<br/><i>src/crawler/config.py</i>"]
    YAML[("configs/crawler.yaml")] --> CFG
    MAIN -->|"for each enabled source"| RUN["run_source()<br/><i>scripts/crawl.py</i>"]

    RUN --> REG["SPIDER_REGISTRY[name]<br/><i>src/crawler/spiders/__init__.py</i>"]
    REG --> SPIDER["TgddSpider / CellphonesSpider<br/><i>src/crawler/spiders/*_spider.py</i>"]
    RUN --> PIPE["CrawlPipeline(config)<br/><i>src/crawler/pipeline.py</i>"]
    RUN --> PRUN["pipeline.run(spider, categories)<br/><i>src/crawler/pipeline.py</i>"]

    PRUN --> GS["config.get_source(name)<br/><i>src/crawler/config.py</i>"]
    PRUN --> HTTP["HttpClient(config)<br/><i>src/crawler/http_client.py</i>"]
    HTTP --> RL["RateLimiter<br/><i>src/crawler/rate_limiter.py</i>"]
    HTTP --> ROB["RobotsChecker<br/><i>src/crawler/robots.py</i>"]
    PRUN --> BIND["spider.bind(client, source_cfg)<br/><i>src/crawler/spiders/base_spider.py</i>"]

    PRUN -->|"for each category"| DISC["spider.discover(category)<br/><i>src/crawler/spiders/base_spider.py</i>"]
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

## Step-by-step

| # | Step | Function | File |
|---|------|----------|------|
| 1 | Parse CLI args (`--source`, `--category`, `--all`, `--config`) | `parse_args()` | `scripts/crawl.py` |
| 2 | Load crawler config from YAML | `CrawlerConfig.from_yaml()` | `src/crawler/config.py` |
| 3 | Resolve targets: one source, or all enabled sources | `main()` | `scripts/crawl.py` |
| 4 | Look up spider class for the source | `SPIDER_REGISTRY[name]` | `src/crawler/spiders/__init__.py` |
| 5 | Build the pipeline and run it | `CrawlPipeline.run()` | `src/crawler/pipeline.py` |
| 6 | Open HTTP client (retry + rate limit + robots.txt) | `HttpClient` | `src/crawler/http_client.py` |
| 7 | Discover product URLs per category (list pages, pagination) | `BaseSpider.discover()` | `src/crawler/spiders/base_spider.py` |
| 8 | Fetch detail pages concurrently and parse products | `BaseSpider.crawl_details()` → `parse_detail()` | `src/crawler/spiders/base_spider.py`, `*_spider.py` |
| 9 | Collect reviews for each product (optional hook) | `BaseSpider.collect_reviews()` | `src/crawler/spiders/base_spider.py` |
| 10 | Save timestamped run + `latest.json` snapshot | `CrawlStorage.save()` | `src/crawler/storage.py` |

## Output

Each run writes two files per source under `data/raw/crawled/<source>/`:
a timestamped `YYYYMMDD_HHMMSS.json` (full `CrawlResult`, including errors) and
`latest.json` (products only) — the file that `scripts/ingest.py` reads by default.
