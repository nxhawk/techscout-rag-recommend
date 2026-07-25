"""
Crawler - Thu thập dữ liệu sản phẩm từ các trang thương mại điện tử.

Public API:
    from src.crawler import CrawlerConfig, HttpClient, CrawlPipeline
    from src.crawler.spiders import TgddSpider, CellphonesSpider
"""
from src.crawler.config import CrawlerConfig
from src.crawler.exceptions import CrawlerError, FetchError, ParseError, RobotsDisallowed
from src.crawler.http_client import HttpClient
from src.crawler.models import CrawledProduct, CrawlResult
from src.crawler.pipeline import CrawlPipeline

__all__ = [
    "CrawlPipeline",
    "CrawlResult",
    "CrawledProduct",
    "CrawlerConfig",
    "CrawlerError",
    "FetchError",
    "HttpClient",
    "ParseError",
    "RobotsDisallowed",
]
