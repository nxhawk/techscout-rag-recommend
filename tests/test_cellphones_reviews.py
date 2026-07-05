"""Unit tests for the CellphoneS comment GraphQL review collection (offline).

The endpoint and response shape were verified against real network captures
(see scripts/discover_reviews_api.py): POST to graphql-customer with a
COMMENTS query; the parent product id comes from the static detail HTML
(`<div id="block-comment-cps" product-id="...">`).
"""
import json

from src.crawler.config import CrawlerConfig, SourceConfig
from src.crawler.models import CrawledProduct
from src.crawler.spiders.cellphones_spider import CellphonesSpider

ENDPOINT = "https://api.cellphones.com.vn/graphql-customer/graphql/query"


class _FakePostClient:
    """Stand-in for HttpClient capturing post_json calls."""

    def __init__(self, config: CrawlerConfig, body: str = "{}"):
        self.config = config
        self._body = body
        self.posted: list[tuple[str, dict]] = []

    def post_json(self, url: str, payload: dict) -> str:
        self.posted.append((url, payload))
        return self._body

    def get(self, url: str) -> str:  # pragma: no cover - not used here
        raise AssertionError("comment API must be POSTed, not GET")


def _bind(client=None, **source_kwargs) -> CellphonesSpider:
    spider = CellphonesSpider()
    src = SourceConfig(
        name="cellphones", base_url="https://cellphones.com.vn", **source_kwargs
    )
    spider.bind(client=client, source=src)
    return spider


def _product() -> CrawledProduct:
    return CrawledProduct(
        id="cellphones-iphone-16-pro-max",
        name="iPhone 16 Pro Max",
        source="cellphones",
        source_url="https://cellphones.com.vn/iphone-16-pro-max.html",
    )


_GRAPHQL_COMMENTS_RESPONSE = json.dumps(
    {
        "data": {
            "comment": {
                "total": 852,
                "matches": [
                    {
                        "id": 1,
                        "content": "Máy dùng rất ổn, pin trâu",
                        "is_shown": 1,
                        "is_admin": 0,
                        "customer": {"fullname": "Nguyen Anh"},
                    },
                    {
                        "id": 2,
                        "content": "Cảm ơn bạn đã ủng hộ CellphoneS",
                        "is_shown": 1,
                        "is_admin": 1,  # staff reply -> skipped
                        "customer": {"fullname": "Quản trị viên"},
                    },
                    {
                        "id": 3,
                        "content": "",  # empty -> skipped
                        "is_shown": 1,
                        "is_admin": 0,
                        "customer": {"fullname": "X"},
                    },
                ],
            }
        }
    },
    ensure_ascii=False,
)

_DETAIL_HTML = """
<html><body>
  <h1>iPhone 16 Pro Max</h1>
  <div id="block-comment-cps" product-id="59258" class="comment-container"></div>
</body></html>
"""


def test_page_product_id_extracted_from_comment_block():
    spider = _bind()
    assert spider._page_product_id(_DETAIL_HTML) == 59258
    assert spider._page_product_id("<html></html>") is None


def test_page_product_id_prefers_comment_block_over_generic_attr():
    """Regression: variant ids in earlier elements must not shadow the parent id."""
    html = """
    <div class="color-option" product-id="90169"></div>
    <div id="block-comment-cps" product-id="59258"></div>
    """
    spider = _bind()
    assert spider._page_product_id(html) == 59258


def test_fetch_endpoint_reviews_posts_graphql_and_parses():
    client = _FakePostClient(
        CrawlerConfig(fetch_reviews=True, max_reviews=20),
        body=_GRAPHQL_COMMENTS_RESPONSE,
    )
    spider = _bind(client=client, reviews_url=ENDPOINT)
    reviews = spider.fetch_endpoint_reviews(_product(), _DETAIL_HTML)

    # Only the real customer comment survives (staff + empty skipped).
    assert len(reviews) == 1
    assert reviews[0].author == "Nguyen Anh"
    assert reviews[0].content == "Máy dùng rất ổn, pin trâu"

    # The GraphQL query embeds page URL, parent product id and query type.
    url, payload = client.posted[0]
    assert url == ENDPOINT
    assert 'type: "product"' in payload["query"]
    assert "productId: 59258" in payload["query"]
    assert "iphone-16-pro-max.html" in payload["query"]


def test_fetch_endpoint_reviews_skipped_without_product_id():
    client = _FakePostClient(CrawlerConfig(fetch_reviews=True))
    spider = _bind(client=client, reviews_url=ENDPOINT)
    product = CrawledProduct(
        id="cellphones-x",
        name="X",
        source="cellphones",
        source_url="https://cellphones.com.vn/x.html",
    )
    assert spider.fetch_endpoint_reviews(product, "<html></html>") == []
    assert client.posted == []


def test_fetch_endpoint_reviews_disabled_without_reviews_url():
    client = _FakePostClient(CrawlerConfig(fetch_reviews=True))
    spider = _bind(client=client)  # no reviews_url configured
    assert spider.fetch_endpoint_reviews(_product(), _DETAIL_HTML) == []
    assert client.posted == []


def test_collect_reviews_uses_graphql_endpoint():
    """End-to-end through BaseSpider.collect_reviews with the POST client."""
    client = _FakePostClient(
        CrawlerConfig(fetch_reviews=True, max_reviews=20),
        body=_GRAPHQL_COMMENTS_RESPONSE,
    )
    spider = _bind(client=client, reviews_url=ENDPOINT)
    reviews = spider.collect_reviews(_product(), _DETAIL_HTML)
    assert [r.content for r in reviews] == ["Máy dùng rất ổn, pin trâu"]


def test_reviews_query_type_configurable():
    client = _FakePostClient(
        CrawlerConfig(fetch_reviews=True), body=_GRAPHQL_COMMENTS_RESPONSE
    )
    spider = _bind(client=client, reviews_url=ENDPOINT, reviews_query_type="rating")
    spider.fetch_endpoint_reviews(_product(), _DETAIL_HTML)
    assert 'type: "rating"' in client.posted[0][1]["query"]


def test_parse_reviews_payload_generic_fallback_still_works():
    spider = _bind()
    body = '{"comments": [{"fullname": "An", "rating": 5, "content": "Tốt"}]}'
    reviews = spider.parse_reviews_payload(body, "https://x/reviews")
    assert len(reviews) == 1
    assert reviews[0].author == "An"
    assert reviews[0].rating == 5.0
