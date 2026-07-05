"""Unit tests for the CellphoneS spider (no network access required).

The live site is a Nuxt app whose class names churn often, so the spider
extracts fields from JSON-LD structured data, meta tags, inline JS state and
server-rendered text patterns. These tests cover each fallback layer.
"""
from src.crawler.config import SourceConfig
from src.crawler.parser import (
    find_product_json_ld,
    json_ld_price,
    json_ld_rating,
    make_soup,
    price_from_inline_json,
    rating_summary_from_text,
)
from src.crawler.spiders.cellphones_spider import CellphonesSpider


def _bind_cellphones(client=None, **source_kwargs):
    spider = CellphonesSpider()
    src = SourceConfig(
        name="cellphones", base_url="https://cellphones.com.vn", **source_kwargs
    )
    spider.bind(client=client, source=src)
    return spider


_CPS_JSON_LD = """
    <script type="application/ld+json">
    {
      "@context": "https://schema.org",
      "@type": "Product",
      "name": "iPhone 16 Pro Max 256GB",
      "image": ["https://cdn2.cellphones.com.vn/x/iphone-16-pro-max.png"],
      "description": "iPhone 16 Pro Max thiết kế titan, màn hình 6.9 inch.",
      "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.9", "reviewCount": "366"},
      "offers": {"@type": "Offer", "price": "30990000", "priceCurrency": "VND"},
      "review": [
        {
          "@type": "Review",
          "author": {"@type": "Person", "name": "Nguyễn An"},
          "reviewRating": {"@type": "Rating", "ratingValue": "5"},
          "reviewBody": "Máy đẹp, camera xuất sắc"
        }
      ]
    }
    </script>
"""


def test_parse_detail_from_json_ld():
    spider = _bind_cellphones()
    html = f"""
    <html><head>{_CPS_JSON_LD}</head><body>
      <h1>Điện thoại iPhone 16 Pro Max 256GB</h1>
    </body></html>
    """
    product = spider.parse_detail(html, "https://cellphones.com.vn/iphone-16-pro-max.html")
    assert product is not None
    assert product.id == "cellphones-iphone-16-pro-max"
    assert product.price == 30990000
    assert product.avg_rating == 4.9
    assert product.review_count == 366
    assert "titan" in product.description
    assert product.image_url == "https://cdn2.cellphones.com.vn/x/iphone-16-pro-max.png"
    assert product.brand == "Apple"


def test_parse_detail_fallbacks_without_json_ld():
    """No JSON-LD: meta description, rating text pattern and VND price text."""
    spider = _bind_cellphones()
    html = """
    <html><head>
      <meta property="og:description" content="iPhone 16 Pro Max chính hãng VN/A.">
      <meta property="og:image" content="https://cdn2.cellphones.com.vn/x/i16pm.png">
    </head><body>
      <h1>Điện thoại iPhone 16 Pro Max 256GB</h1>
      <div class="some-rating-box">4.9 (366 đánh giá)</div>
      <div class="whatever">30.990.000đ <s>34.990.000đ</s></div>
    </body></html>
    """
    product = spider.parse_detail(html, "https://cellphones.com.vn/iphone-16-pro-max.html")
    assert product is not None
    assert product.price == 30990000
    assert product.avg_rating == 4.9
    assert product.review_count == 366
    assert product.description == "iPhone 16 Pro Max chính hãng VN/A."
    assert product.image_url == "https://cdn2.cellphones.com.vn/x/i16pm.png"


def test_price_from_inline_json_state():
    spider = _bind_cellphones()
    html = """
    <html><body>
      <h1>POCO X8 Pro Max</h1>
      <script>window.__STATE__={"product":{"special_price":8490000,"sku":"X8PM"}};</script>
    </body></html>
    """
    product = spider.parse_detail(html, "https://cellphones.com.vn/poco-x8-pro-max.html")
    assert product is not None
    assert product.price == 8490000


def test_reviews_from_json_ld():
    spider = _bind_cellphones()
    html = f"<html><head>{_CPS_JSON_LD}</head><body><h1>iPhone 16 Pro Max</h1></body></html>"
    reviews = spider.parse_reviews(html, "https://cellphones.com.vn/iphone-16-pro-max.html")
    assert len(reviews) == 1
    assert reviews[0].author == "Nguyễn An"
    assert reviews[0].rating == 5.0
    assert reviews[0].content == "Máy đẹp, camera xuất sắc"


def test_image_skips_placeholder():
    spider = _bind_cellphones()
    html = """
    <html><body>
      <h1>iPhone 16 Pro Max</h1>
      <div class="swiper-slide"><img src="https://cdn2.cellphones.com.vn/media/wysiwyg/placehoder.png"
           data-src="https://cdn2.cellphones.com.vn/x/real.png"></div>
    </body></html>
    """
    product = spider.parse_detail(html, "https://cellphones.com.vn/iphone-16-pro-max.html")
    assert product is not None
    assert product.image_url == "https://cdn2.cellphones.com.vn/x/real.png"


# -- Structured-data parser helpers -------------------------------------------


def test_find_product_json_ld_handles_graph_and_lists():
    html = """
    <script type="application/ld+json">
    {"@graph": [{"@type": "BreadcrumbList"}, {"@type": ["Product"], "name": "X"}]}
    </script>
    """
    ld = find_product_json_ld(make_soup(html))
    assert ld.get("name") == "X"


def test_json_ld_price_variants():
    assert json_ld_price({"offers": {"price": "30990000"}}) == 30990000
    assert json_ld_price({"offers": [{"lowPrice": 8490000}]}) == 8490000
    assert json_ld_price({"offers": {"price": ""}}) == 0
    assert json_ld_price({}) == 0


def test_json_ld_rating():
    assert json_ld_rating(
        {"aggregateRating": {"ratingValue": "4.9", "reviewCount": "366"}}
    ) == (4.9, 366)
    assert json_ld_rating({}) == (0.0, 0)


def test_rating_summary_from_text():
    assert rating_summary_from_text("4.9 (366 đánh giá)") == (4.9, 366)
    assert rating_summary_from_text("4,5 (1.234 lượt đánh giá)") == (4.5, 1234)
    assert rating_summary_from_text("no rating here") == (0.0, 0)


def test_price_from_inline_json():
    assert price_from_inline_json('{"special_price":30990000}') == 30990000
    assert price_from_inline_json('{"final_price": "8490000"}') == 8490000
    assert price_from_inline_json('{"price": 99}') == 0  # too short to be VND
    assert price_from_inline_json("") == 0
