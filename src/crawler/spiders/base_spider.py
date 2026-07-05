"""
Base Spider - Lớp cơ sở cho tất cả spider.

Required hooks (per source):
    - build_list_url(category, page): construct a listing page URL
    - parse_list(html, base_url):     extract product detail URLs from a listing
    - parse_detail(html, url):        extract a CrawledProduct from a detail page

Optional review hooks (override to collect buyer reviews):
    - parse_reviews(html, url):       reviews embedded in the detail page HTML
    - build_reviews_url(product):     URL of the site's review endpoint (or None)
    - parse_reviews_payload(body, url): reviews from the endpoint response (JSON/HTML)

The base class handles pagination, concurrent detail fetching, review collection
(gated by config), deduplication, capping and error capture.
"""
from abc import ABC, abstractmethod
from collections.abc import Iterator

from src.crawler.config import SourceConfig
from src.crawler.exceptions import CrawlerError
from src.crawler.http_client import HttpClient
from src.crawler.models import CrawledProduct, Review
from src.crawler.parser import make_soup
from src.utils.logger import setup_logger


class BaseSpider(ABC):
    """Abstract spider. Set the class attribute `name` in each subclass."""

    name: str = "base"

    def __init__(self) -> None:
        self._client: HttpClient | None = None
        self._source: SourceConfig | None = None
        self.logger = setup_logger(f"crawler.spider.{self.name}")

    # -- Lifecycle -----------------------------------------------------------

    def bind(self, client: HttpClient, source: SourceConfig) -> None:
        """Attach the HTTP client and source config (called by the pipeline)."""
        self._client = client
        self._source = source

    @property
    def client(self) -> HttpClient:
        if self._client is None:
            raise CrawlerError("Spider not bound to an HttpClient. Call bind() first.")
        return self._client

    @property
    def source(self) -> SourceConfig:
        if self._source is None:
            raise CrawlerError("Spider not bound to a SourceConfig. Call bind() first.")
        return self._source

    # -- Hooks to implement in subclasses ------------------------------------

    @abstractmethod
    def build_list_url(self, category: str, page: int) -> str:
        """Return the listing URL for a category and 1-based page number."""

    @abstractmethod
    def parse_list(self, html: str, base_url: str) -> list[str]:
        """Return absolute product detail URLs found on a listing page."""

    @abstractmethod
    def parse_detail(self, html: str, url: str) -> CrawledProduct | None:
        """Return a CrawledProduct parsed from a detail page, or None to skip."""

    # -- Optional review hooks (default: no reviews) -------------------------

    def parse_reviews(self, html: str, url: str) -> list[Review]:
        """Return reviews embedded in the detail page HTML. Override to enable."""
        return []

    def build_reviews_url(self, product: CrawledProduct) -> str | None:
        """Return the review-endpoint URL for a product, or None if unused.

        Default implementation uses `SourceConfig.reviews_url` as a template
        with `{product_id}`, `{slug}` and `{page}` placeholders.
        """
        template = self.source.reviews_url
        if not template:
            return None
        slug = product.source_url.rstrip("/").split("/")[-1].split("?")[0]
        return template.format(product_id=product.id, slug=slug, page=1)

    def parse_reviews_payload(self, body: str, url: str) -> list[Review]:
        """Return reviews parsed from the review-endpoint response. Override."""
        return []

    def fetch_endpoint_reviews(
        self, product: CrawledProduct, detail_html: str
    ) -> list[Review]:
        """Fetch reviews from the source's review endpoint.

        Default: GET `build_reviews_url(product)` and parse the body. Override
        for sources whose endpoint needs a POST body or page-derived params
        (`detail_html` is provided for extracting those).
        """
        endpoint = self.build_reviews_url(product)
        if not endpoint:
            return []
        body = self.client.get(endpoint)
        return self.parse_reviews_payload(body, endpoint)

    # -- Review collection (shared) ------------------------------------------

    def collect_reviews(self, product: CrawledProduct, detail_html: str) -> list[Review]:
        """Gather reviews for a product: inline HTML first, then the endpoint.

        Gated by `config.fetch_reviews`, deduplicated and capped at
        `config.max_reviews`. Endpoint failures are logged and skipped.
        """
        config = self.client.config
        if not config.fetch_reviews:
            return []

        reviews: list[Review] = list(self.parse_reviews(detail_html, product.source_url))

        if len(reviews) < config.max_reviews:
            try:
                reviews.extend(self.fetch_endpoint_reviews(product, detail_html))
            except CrawlerError as exc:
                self.logger.warning(
                    "reviews fetch failed for %s: %s", product.source_url, exc
                )

        # Deduplicate (by author + content) while preserving order, then cap.
        seen: set[tuple[str, str]] = set()
        unique: list[Review] = []
        for review in reviews:
            k = review.key()
            if k in seen:
                continue
            seen.add(k)
            unique.append(review)
        return unique[: config.max_reviews]

    # -- Driving logic (shared) ----------------------------------------------

    def discover(self, category: str) -> list[str]:
        """Walk listing pages for a category and collect unique detail URLs.

        Stops early when a page yields no *new* URLs (empty page, or a site that
        keeps returning page 1 for every `?page=` value) or once `max_products`
        unique URLs have been gathered.
        """
        target = self.source.max_products or None
        seen: set[str] = set()
        urls: list[str] = []
        for page in range(1, self.source.max_pages + 1):
            list_url = self.build_list_url(category, page)
            html = self.client.get(list_url)
            new = [u for u in self.parse_list(html, list_url) if u not in seen]
            if not new:
                break  # no new results -> stop paginating
            for u in new:
                seen.add(u)
                urls.append(u)
            if target is not None and len(urls) >= target:
                break
        return urls[:target] if target is not None else urls

    def crawl_details(self, urls: list[str]) -> Iterator[CrawledProduct | None]:
        """Fetch detail pages concurrently, parse products and attach reviews."""
        import asyncio

        htmls = asyncio.run(self.client.get_many(urls))
        for url, html in zip(urls, htmls):
            if html is None:
                continue
            try:
                product = self.parse_detail(html, url)
            except Exception as exc:  # keep the run going on a single bad page
                self.logger.warning("parse_detail failed for %s: %s", url, exc)
                continue
            if product is not None:
                try:
                    product.reviews = self.collect_reviews(product, html)
                    product.review_count = product.review_count or len(product.reviews)
                except Exception as exc:  # reviews are best-effort
                    self.logger.warning("collect_reviews failed for %s: %s", url, exc)
            yield product

    # -- Convenience ----------------------------------------------------------

    def soup(self, html: str):
        """Shortcut to build a BeautifulSoup tree."""
        return make_soup(html)
