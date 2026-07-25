"""
Spiders - Mỗi spider định nghĩa cách crawl một nguồn cụ thể.

Registry maps a source name to its spider class so the CLI can look them up.
"""
from src.crawler.spiders.base_spider import BaseSpider
from src.crawler.spiders.cellphones_spider import CellphonesSpider
from src.crawler.spiders.tgdd_spider import TgddSpider

SPIDER_REGISTRY: dict[str, type[BaseSpider]] = {
    TgddSpider.name: TgddSpider,
    CellphonesSpider.name: CellphonesSpider,
}

__all__ = ["SPIDER_REGISTRY", "BaseSpider", "CellphonesSpider", "TgddSpider"]
