"""
CellphoneS Spider - Crawl sản phẩm từ cellphones.com.vn.

Extraction strategy (most to least reliable):
    1. JSON-LD Product structured data (<script type="application/ld+json">) —
       price, rating, review count, description, image and SEO reviews.
    2. <meta> tags (og:description, og:image, product:price:amount).
    3. Inline JS state (e.g. Nuxt) via a price-key regex.
    4. Text patterns rendered server-side, e.g. the "4.9 (366 đánh giá)" summary
       next to the title and the first VND price in the buy box.
    5. CSS selectors as a last resort — the site is a Nuxt app and its class
       names churn often, so selectors alone are NOT trusted.

Buyer reviews are rendered client-side and are not present in the static HTML.
They are fetched from the site's comment GraphQL API (verified via network
capture): POST to `reviews_url` (api.cellphones.com.vn/graphql-customer) with a
COMMENTS query. The query needs the page-level (parent) product id, which the
static HTML exposes as `<div id="block-comment-cps" product-id="...">`.
JSON-LD SEO reviews are also collected when they carry text.
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.crawler.models import CrawledProduct, Review
from src.crawler.parser import (
    clean_ws,
    find_product_json_ld,
    find_review_list,
    flatten_spec_groups,
    json_ld_price,
    json_ld_rating,
    json_ld_reviews,
    json_loads_safe,
    make_soup,
    meta_content,
    parse_price,
    parse_rating,
    parse_spec_groups,
    pick,
    price_from_inline_json,
    rating_summary_from_text,
    review_content,
    select_text,
    star_rating,
)
from src.crawler.spiders.base_spider import BaseSpider
from src.utils.helpers import detect_brand

# JSON keys review endpoints tend to use (checked case-insensitively).
_LIST_KEYS = ("comments", "reviews", "data", "items", "listComment")
_AUTHOR_KEYS = ("fullname", "name", "customername", "author", "username")
_CONTENT_KEYS = ("content", "comment", "body", "message", "text")
_RATING_KEYS = ("rating", "star", "stars", "point", "score")

# Page-level (parent) product id rendered in the static comment container:
#   <div id="block-comment-cps" product-id="59258" ...>
# The anchored pattern MUST be tried first: other elements carry a generic
# product-id attribute holding the variant id, which the comment API rejects.
_PAGE_PRODUCT_ID_RES = (
    re.compile(r"""id=["']block-comment-cps["'][^>]*\sproduct-id=["'](\d+)["']"""),
    re.compile(r"""product-id=["'](\d+)["']"""),
)

# GraphQL COMMENTS query, replicated from the site's own network traffic.
# `type` is configurable ("product" = Q&A/comment feed).
_COMMENTS_QUERY_TEMPLATE = """query COMMENTS {{
  comment(
    type: "{query_type}",
    pageUrl: "{page_url}",
    productId: {product_id},
    currentPage: {page}
  ) {{
    total
    matches {{
      id
      content
      is_shown
      is_admin
      created_at
      customer {{
        fullname
      }}
    }}
  }}
}}"""

# First VND-formatted amount, e.g. "30.990.000đ" / "30.990.000 ₫".
_VND_PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3}){1,3})\s*[₫đ]")

# Image URLs that are lazy-load placeholders, not real product shots.
_PLACEHOLDER_IMAGE_RE = re.compile(r"placeh|youtube|\.gif($|\?)", re.IGNORECASE)


class CellphonesSpider(BaseSpider):
    """Spider for cellphones.com.vn (static HTML listing + detail pages)."""

    name = "cellphones"

    def build_list_url(self, category: str, page: int) -> str:
        template = self.source.categories[category]
        path = template.format(page=page)
        return urljoin(self.source.base_url, path)

    def parse_list(self, html: str, base_url: str) -> list[str]:
        soup = self.soup(html)
        urls: list[str] = []
        # Product cards: <div class="product-info"> <a class="product__link" href>
        for a in soup.select("a.product__link, .product-info a[href], .product-item a[href]"):
            href = a.get("href")
            if href:
                urls.append(urljoin(self.source.base_url, href))
        return [u for u in dict.fromkeys(urls) if u.startswith("http")]

    def parse_detail(self, html: str, url: str) -> CrawledProduct | None:
        soup = self.soup(html)

        name = select_text(soup, "h1")
        if not name:
            return None

        product_ld = find_product_json_ld(soup)

        price = self._extract_price(soup, html, product_ld)
        rating, review_count = self._extract_rating(soup, product_ld)
        description = self._extract_description(soup, product_ld)
        image = self._extract_image(soup, product_ld)

        spec_groups = self._parse_spec_groups(soup)
        specs = flatten_spec_groups(spec_groups)

        product_id = self._slug_from_url(url)
        return CrawledProduct(
            id=f"{self.name}-{product_id}",
            name=name,
            source=self.name,
            source_url=url,
            brand=detect_brand(name),
            category="smartphone",
            price=price,
            specifications=specs,
            spec_groups=spec_groups,
            description=description,
            image_url=image,
            avg_rating=rating,
            review_count=review_count,
        )

    # -- Field extraction (layered fallbacks) ---------------------------------

    _PRICE_SELECTOR = (
        ".tpt---sale-price, .tpt---price, .product__price--show, "
        ".box-info__box-price, .sale-price, .special-price, "
        "[class*='sale-price'], [class*='special-price'], [class*='box-price']"
    )
    _DESCRIPTION_SELECTOR = (
        ".ksp-content, .product-description, #cpsContent, "
        ".cps-block-content, .block-content-product"
    )
    _IMAGE_SELECTOR = ".swiper-slide img, .product-image img, .box-gallery img"

    def _extract_price(self, soup: BeautifulSoup, html: str, product_ld: dict) -> int:
        """Price in VND: JSON-LD -> meta -> price-ish elements -> inline JSON -> text."""
        price = json_ld_price(product_ld)
        if price:
            return price
        price = parse_price(
            meta_content(soup, "product:price:amount", "og:price:amount", "price")
        )
        if price:
            return price
        price = parse_price(select_text(soup, self._PRICE_SELECTOR))
        if price:
            return price
        price = price_from_inline_json(html)
        if price:
            return price
        # Last resort: first VND-formatted amount in the page body text.
        match = _VND_PRICE_RE.search(soup.get_text(" "))
        return parse_price(match.group(0)) if match else 0

    def _extract_rating(self, soup: BeautifulSoup, product_ld: dict) -> tuple[float, int]:
        """(avg_rating, review_count): JSON-LD -> '4.9 (366 đánh giá)' text pattern."""
        rating, count = json_ld_rating(product_ld)
        if rating or count:
            return rating, count
        # The summary is rendered next to <h1>; search the whole page text so we
        # do not depend on its container class.
        return rating_summary_from_text(soup.get_text(" "))

    def _extract_description(self, soup: BeautifulSoup, product_ld: dict) -> str:
        """Description: JSON-LD -> og/meta description -> known containers."""
        description = product_ld.get("description")
        if isinstance(description, str) and description.strip():
            return clean_ws(description)
        description = meta_content(soup, "og:description", "description")
        if description:
            return description
        return select_text(soup, self._DESCRIPTION_SELECTOR)

    def _extract_image(self, soup: BeautifulSoup, product_ld: dict) -> str:
        """Image URL: JSON-LD -> og:image -> gallery <img>, skipping placeholders."""
        image = product_ld.get("image")
        if isinstance(image, list):
            image = next((i for i in image if isinstance(i, str)), "")
        if isinstance(image, str) and image.strip():
            return image.strip()
        image = meta_content(soup, "og:image", "og:image:secure_url")
        if image and not _PLACEHOLDER_IMAGE_RE.search(image):
            return image
        for img in soup.select(self._IMAGE_SELECTOR):
            src = img.get("data-src") or img.get("src") or ""
            if isinstance(src, str) and src and not _PLACEHOLDER_IMAGE_RE.search(src):
                return src
        return image or ""

    def _parse_spec_groups(self, soup: BeautifulSoup) -> dict[str, dict[str, str]]:
        """Extract the spec table grouped by category, normalized to canonical keys."""
        root = soup.select_one(
            ".technical-content, .box-specification, .cps-block-content, "
            ".cps-block-content__box, table.table"
        )
        groups = parse_spec_groups(
            root,
            title_selector="h3, h4, .title, .box-specification__title, .group-title",
            row_selector="tr, li",
            label_selector="td:first-child, th, .label",
            value_selector="td:last-child, .value",
        )
        if groups:
            return groups
        general: dict[str, str] = {}
        for row in soup.select(
            ".technical-content tr, .box-specification tr, table.table tr"
        ):
            label = select_text(row, "td:first-child, th, .label")
            value = select_text(row, "td:last-child, .value")
            if label and value and label != value:
                general[clean_ws(label)] = clean_ws(value)
        return {"general": general} if general else {}

    # -- Reviews -------------------------------------------------------------

    _REVIEW_BLOCK_SELECTOR = (
        ".comment-item, .box-review__item, .review-item, .product-comment__item, "
        "[class*='review-item'], [class*='comment-item']"
    )
    _AUTHOR_SELECTOR = ".comment-author, .review-author, .rc-name, .name, .author, b, strong"
    _CONTENT_SELECTORS = (".comment-content", ".review-content", ".rc-content", ".content-comment")

    def parse_reviews(self, html: str, url: str) -> list[Review]:
        """Parse reviews from the detail page: DOM blocks plus JSON-LD SEO reviews.

        Buyer reviews are hydrated client-side on this site, so the DOM pass
        usually finds nothing in static HTML; JSON-LD is the reliable source.
        """
        soup = make_soup(html)
        reviews: list[Review] = []
        for node in soup.select(self._REVIEW_BLOCK_SELECTOR):
            author = select_text(node, self._AUTHOR_SELECTOR)
            rating = star_rating(node)
            content = review_content(node, author, content_selectors=self._CONTENT_SELECTORS)
            if content and content != author:
                reviews.append(Review(author=author, rating=rating, content=content))
        for record in json_ld_reviews(find_product_json_ld(soup)):
            reviews.append(
                Review(
                    author=record["author"],
                    rating=record["rating"],
                    content=record["content"],
                )
            )
        return reviews

    def build_reviews_url(self, product: CrawledProduct) -> str | None:
        """The comment API is a fixed GraphQL endpoint (no per-product URL)."""
        return self.source.reviews_url or None

    def fetch_endpoint_reviews(
        self, product: CrawledProduct, detail_html: str
    ) -> list[Review]:
        """POST the COMMENTS GraphQL query for this product and parse replies."""
        endpoint = self.source.reviews_url
        if not endpoint:
            return []
        page_product_id = self._page_product_id(detail_html)
        if page_product_id is None:
            self.logger.warning(
                "no page product id in detail HTML for %s; skipping reviews",
                product.source_url,
            )
            return []
        query = _COMMENTS_QUERY_TEMPLATE.format(
            query_type=self.source.reviews_query_type,
            page_url=product.source_url,
            product_id=page_product_id,
            page=1,
        )
        body = self.client.post_json(endpoint, {"query": query, "variables": {}})
        return self.parse_reviews_payload(body, endpoint)

    @staticmethod
    def _page_product_id(html: str) -> int | None:
        """Extract the parent product id from the static comment container."""
        for pattern in _PAGE_PRODUCT_ID_RES:
            match = pattern.search(html or "")
            if match:
                return int(match.group(1))
        return None

    def parse_reviews_payload(self, body: str, url: str) -> list[Review]:
        """Parse reviews from the comment endpoint (GraphQL first, then generic)."""
        data = json_loads_safe(body)
        if data is None:
            return self.parse_reviews(body, url)

        # Verified GraphQL shape: {"data": {"comment": {"total": N, "matches": [...]}}}
        matches = data
        for key in ("data", "comment", "matches"):
            matches = matches.get(key) if isinstance(matches, dict) else None
            if matches is None:
                break
        if isinstance(matches, list):
            return self._reviews_from_matches(matches)

        # Generic fallback for other/legacy payload shapes.
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

    def _reviews_from_matches(self, matches: list) -> list[Review]:
        """Map GraphQL comment matches to Reviews, skipping staff/hidden entries."""
        reviews: list[Review] = []
        for record in matches:
            if not isinstance(record, dict):
                continue
            if record.get("is_admin") or record.get("is_shown") == 0:
                continue
            content = clean_ws(str(record.get("content") or ""))
            if not content:
                continue
            customer = record.get("customer")
            author = ""
            if isinstance(customer, dict):
                author = clean_ws(str(customer.get("fullname") or ""))
            rating = parse_rating(pick(record, _RATING_KEYS))
            reviews.append(Review(author=author, rating=rating, content=content))
        return reviews

    @staticmethod
    def _slug_from_url(url: str) -> str:
        return url.rstrip("/").split("/")[-1].split("?")[0].replace(".html", "")
