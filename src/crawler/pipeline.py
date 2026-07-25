"""
Pipeline - Điều phối quá trình crawl: spider -> product -> lưu trữ.
"""
from datetime import UTC, datetime

from src.crawler.config import CrawlerConfig
from src.crawler.exceptions import CrawlerError
from src.crawler.http_client import HttpClient
from src.crawler.models import CrawlResult
from src.crawler.spiders.base_spider import BaseSpider
from src.crawler.storage import CrawlStorage
from src.utils.logger import setup_logger

logger = setup_logger("crawler.pipeline")


class CrawlPipeline:
    """Run a spider end-to-end and persist the results.

    Steps: discover product URLs (list pages) -> fetch detail pages -> parse
    into CrawledProduct -> save via CrawlStorage.
    """

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.storage = CrawlStorage(config.output_dir)

    def run(self, spider: BaseSpider, categories: list[str] | None = None) -> CrawlResult:
        """Execute the crawl for the given spider and categories."""
        result = CrawlResult(source=spider.name)
        source_cfg = self.config.get_source(spider.name)
        targets = categories or list(source_cfg.categories.keys())

        with HttpClient(self.config) as client:
            spider.bind(client, source_cfg)

            product_urls: list[str] = []
            for category in targets:
                try:
                    urls = spider.discover(category)
                    logger.info("[%s/%s] found %d product URLs", spider.name, category, len(urls))
                    product_urls.extend(urls)
                except CrawlerError as exc:
                    result.errors.append(f"discover({category}): {exc}")
                    logger.warning("discover failed for %s: %s", category, exc)

            # Deduplicate while preserving order.
            product_urls = list(dict.fromkeys(product_urls))
            if source_cfg.max_products:
                product_urls = product_urls[: source_cfg.max_products]

            for product in spider.crawl_details(product_urls):
                if product is not None:
                    result.products.append(product)

        result.finished_at = datetime.now(tz=UTC).isoformat()
        self.storage.save(result)
        logger.info("[%s] done: %d products, %d errors", spider.name, result.count, len(result.errors))
        return result
