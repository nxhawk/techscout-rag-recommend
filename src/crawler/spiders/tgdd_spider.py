"""
TGDĐ Spider - Crawl sản phẩm từ thegioididong.com.

NOTE: CSS selectors reflect the site's markup at the time of writing and are the
most likely thing to break when the site changes. Verify them against the live
DOM before a production run. The parsing itself is defensive: missing fields fall
back to sensible defaults instead of raising.
"""
from urllib.parse import urljoin

from src.constants import Category
from src.crawler.models import CrawledProduct, Review
from src.crawler.parser import (
    clean_ws,
    find_review_list,
    flatten_spec_groups,
    json_loads_safe,
    make_soup,
    parse_price,
    parse_rating,
    parse_spec_groups,
    pick,
    review_content,
    select_attr,
    select_text,
    star_rating,
)
from src.crawler.spiders.base_spider import BaseSpider
from src.utils.helpers import detect_brand

# JSON keys review endpoints tend to use (checked case-insensitively).
_LIST_KEYS = ("comments", "listComment", "data", "items", "reviews")
_AUTHOR_KEYS = ("fullname", "name", "customername", "author", "username")
_CONTENT_KEYS = ("content", "comment", "body", "message", "text")
_RATING_KEYS = ("rating", "star", "stars", "point", "score")


class TgddSpider(BaseSpider):
    """Spider for thegioididong.com (static HTML listing + detail pages)."""

    name = "tgdd"

    def build_list_url(self, category: str, page: int) -> str:
        # source.categories maps category -> listing path template.
        template = self.source.categories[category]
        path = template.format(page=page)
        return urljoin(self.source.base_url, path)

    def parse_list(self, html: str, base_url: str) -> list[str]:
        soup = self.soup(html)
        urls: list[str] = []
        # Product cards on TGDĐ listing pages: <li class="item"> <a href="...">
        for a in soup.select("li.item a.main-contain, ul.listproduct li a[href]"):
            href = a.get("href")
            if href:
                urls.append(urljoin(self.source.base_url, href))
        return [u for u in dict.fromkeys(urls) if u.startswith("http")]

    def parse_detail(self, html: str, url: str) -> CrawledProduct | None:
        soup = self.soup(html)

        name = select_text(soup, "h1")
        if not name:
            return None

        price = parse_price(select_text(soup, ".box-price-present, .price-one, .bs_price strong"))
        rating = parse_rating(select_text(soup, ".rating-avg, .point-average-score"))
        image = select_attr(soup, ".owl-carousel img, .detail-img img", "src")
        description = select_text(soup, ".article-content, .detail-desc")

        spec_groups = self._parse_spec_groups(soup)
        specs = flatten_spec_groups(spec_groups)
        review_count = int(parse_rating(select_text(soup, ".rating-total, .cmt-total")))

        product_id = self._slug_from_url(url)
        return CrawledProduct(
            id=f"{self.name}-{product_id}",
            name=name,
            source=self.name,
            source_url=url,
            brand=detect_brand(name),
            category=Category.SMARTPHONE.value,
            price=price,
            specifications=specs,
            spec_groups=spec_groups,
            description=description,
            image_url=image,
            avg_rating=rating,
            review_count=review_count,
        )

    def _parse_spec_groups(self, soup) -> dict[str, dict[str, str]]:
        """Extract the spec table grouped by category (config, camera, pin, ...).

        TGDĐ groups specs under headings ("Cấu hình & Bộ nhớ", "Camera & Màn hình",
        "Pin & Sạc", "Thiết kế & Chất liệu"). We walk the spec container in order,
        assigning each row to its nearest heading, then normalize headings to
        canonical keys. Falls back to a single "general" group when no container.
        """
        root = soup.select_one(
            ".box-specifi, .parameter, .specification, "
            ".specifi-content, .parameter-content, #productDetailSpecifi"
        )
        groups = parse_spec_groups(
            root,
            title_selector="h3, h4, .title, .header-specifi, .group-title, strong.title",
            row_selector="li, tr",
            label_selector="aside, .label, td:first-child, strong",
            value_selector="span, .value, td:last-child",
        )
        if groups:
            return groups
        # Fallback: no container found -> collect scattered rows into "general".
        general: dict[str, str] = {}
        for row in soup.select(".parameter li, .box-specifi tr, .parameter-content li"):
            label = select_text(row, "aside, .label, td:first-child, strong")
            value = select_text(row, "span, .value, td:last-child")
            if label and value and label != value:
                general[clean_ws(label)] = clean_ws(value)
        return {"general": general} if general else {}

    # -- Reviews -------------------------------------------------------------

    # Selectors for one review block and its author (verify against live DOM).
    _REVIEW_BLOCK_SELECTOR = (
        ".comment-list .par, .item-comment, .comment-item, .boxcmt-item, "
        "[class*='comment-item'], [class*='rating-item'], li[id^='comment']"
    )
    _AUTHOR_SELECTOR = ".cmt-top-name, .comment-author, .rc-name, .author, .name, b, strong"
    _CONTENT_SELECTORS = (".cmt-content", ".comment-content", ".rc-content", ".content-comment")

    def parse_reviews(self, html: str, url: str) -> list[Review]:
        """Parse buyer reviews embedded in the detail page HTML.

        Author comes from a name element; rating and content are extracted with
        the robust helpers so they work even when the exact class names differ
        (content falls back to the block text minus author/badge/footer).
        """
        soup = make_soup(html)
        reviews: list[Review] = []
        for node in soup.select(self._REVIEW_BLOCK_SELECTOR):
            author = select_text(node, self._AUTHOR_SELECTOR)
            rating = star_rating(node)
            content = review_content(node, author, content_selectors=self._CONTENT_SELECTORS)
            if content and content != author:
                reviews.append(Review(author=author, rating=rating, content=content))
        return reviews

    def parse_reviews_payload(self, body: str, url: str) -> list[Review]:
        """Parse reviews from the review endpoint (JSON preferred, HTML fallback)."""
        data = json_loads_safe(body)
        if data is not None:
            reviews: list[Review] = []
            for record in find_review_list(data, _LIST_KEYS):
                content = pick(record, _CONTENT_KEYS)
                if not content:
                    continue
                reviews.append(
                    Review(
                        author=pick(record, _AUTHOR_KEYS),
                        rating=parse_rating(pick(record, _RATING_KEYS)),
                        content=content,
                    )
                )
            return reviews
        # Some endpoints return an HTML fragment instead of JSON.
        return self.parse_reviews(body, url)

    @staticmethod
    def _slug_from_url(url: str) -> str:
        return url.rstrip("/").split("/")[-1].split("?")[0]
