"""Discover the review/rating API endpoints used by cellphones.com.vn.

Buyer reviews on cellphones.com.vn are hydrated client-side, so the static
HTML the crawler fetches never contains them. This one-off dev utility loads
product pages in headless Chromium and records everything needed to wire the
real endpoints into the crawler:

1. Network capture of review-related API calls (scrolling AND clicking the
   rating widget, which only fires its query on interaction).
2. A GraphQL introspection dump of the customer API (comment/rating schema).
3. The raw server-rendered HTML of one detail page (to locate the parent
   product id the queries require).

Usage (requires network access to cellphones.com.vn):
    uv add --dev playwright
    uv run playwright install chromium
    uv run python scripts/discover_reviews_api.py

Output (all under data/raw/crawled/):
    review_api_discovery.json   candidate requests/responses
    introspection_customer.json GraphQL schema of graphql-customer
    raw_detail_page.html        raw (pre-JS) HTML of the first product page
"""
import json
import re
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Response, sync_playwright

PRODUCT_URLS = [
    "https://cellphones.com.vn/iphone-16-pro-max.html",
    "https://cellphones.com.vn/samsung-galaxy-s25-ultra.html",
]

OUTPUT_DIR = Path("data/raw/crawled")
CUSTOMER_API = "https://api.cellphones.com.vn/graphql-customer/graphql/query"

# A request is interesting when its URL or body mentions one of these.
URL_NEEDLES = ("comment", "review", "rating", "danh-gia", "danhgia", "graphql")
# ... or when its JSON response contains review-shaped records.
BODY_NEEDLES = ("rating", "comment", "review", "content", "customer")

# Texts/selectors that open the rating widget (fires the rating query).
RATING_CLICK_TEXTS = ("Xem tất cả đánh giá", "đánh giá", "Đánh giá")
RATING_CLICK_SELECTORS = (
    ".box-rating", "[class*='rating']", "[class*='review']", "#cpsRating",
)

SKIPPED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}
MAX_BODY_CHARS = 4000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

INTROSPECTION_QUERY = {
    "query": (
        "query { __schema { queryType { fields { name description "
        "args { name type { name kind ofType { name } } } "
        "type { name kind ofType { name } } } } } }"
    ),
    "variables": {},
}


def looks_review_related(url: str, body: str) -> bool:
    """Heuristic: URL mentions reviews, or the JSON body has review-ish keys."""
    low_url = url.lower()
    if any(n in low_url for n in URL_NEEDLES):
        return True
    low_body = body[:20000].lower()
    hits = sum(1 for n in BODY_NEEDLES if f'"{n}' in low_body)
    return hits >= 3


def snapshot_response(response: Response) -> dict[str, Any] | None:
    """Serialize one request/response pair, or None if it is not interesting."""
    request = response.request
    if request.resource_type in SKIPPED_RESOURCE_TYPES:
        return None
    content_type = response.headers.get("content-type", "")
    if not re.search(r"json|text|graphql", content_type, re.IGNORECASE):
        return None
    try:
        body = response.text()
    except Exception:  # binary/aborted bodies are irrelevant here
        return None
    if not body or not looks_review_related(response.url, body):
        return None
    return {
        "url": response.url,
        "method": request.method,
        "status": response.status,
        "content_type": content_type,
        "post_data": (request.post_data or "")[:MAX_BODY_CHARS],
        "response_snippet": body[:MAX_BODY_CHARS],
    }


def click_rating_widget(page: Page) -> None:
    """Best-effort clicks that make the page fire its rating/review query."""
    for text in RATING_CLICK_TEXTS:
        try:
            locator = page.get_by_text(text, exact=False).first
            locator.scroll_into_view_if_needed(timeout=3000)
            locator.click(timeout=3000)
            page.wait_for_timeout(2000)
        except Exception:
            continue
    for selector in RATING_CLICK_SELECTORS:
        try:
            locator = page.locator(selector).first
            locator.scroll_into_view_if_needed(timeout=2000)
            locator.click(timeout=2000)
            page.wait_for_timeout(2000)
        except Exception:
            continue


def dump_introspection(page: Page) -> None:
    """POST a GraphQL introspection query and store the schema dump."""
    try:
        response = page.request.post(
            CUSTOMER_API,
            data=json.dumps(INTROSPECTION_QUERY),
            headers={"Content-Type": "application/json"},
        )
        (OUTPUT_DIR / "introspection_customer.json").write_text(
            response.text(), encoding="utf-8"
        )
        print(f"Introspection: HTTP {response.status}")
    except Exception as exc:
        print(f"Introspection failed: {exc}", file=sys.stderr)


def save_raw_html(page: Page, url: str) -> None:
    """Store the raw server response (pre-JS) of a product page."""
    try:
        response = page.request.get(url, headers={"User-Agent": USER_AGENT})
        (OUTPUT_DIR / "raw_detail_page.html").write_text(
            response.text(), encoding="utf-8"
        )
        print(f"Raw HTML saved: HTTP {response.status}")
    except Exception as exc:
        print(f"Raw HTML fetch failed: {exc}", file=sys.stderr)


def discover(product_urls: list[str]) -> list[dict[str, Any]]:
    """Load each product page, scroll + click, and collect candidate calls."""
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=USER_AGENT, locale="vi-VN")

        def on_response(response: Response) -> None:
            snap = snapshot_response(response)
            if snap is None:
                return
            key = (snap["method"], snap["url"].split("?")[0])
            if key in seen and not snap["post_data"]:
                return
            seen.add(key)
            candidates.append(snap)

        page.on("response", on_response)

        save_raw_html(page, product_urls[0])
        dump_introspection(page)

        for url in product_urls:
            print(f"Loading {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                print(f"  navigation failed: {exc}", file=sys.stderr)
                continue
            # Scroll stepwise so lazy sections (incl. the review widget) mount.
            for _ in range(15):
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(700)
            click_rating_widget(page)
            page.wait_for_timeout(3000)

        browser.close()
    return candidates


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = discover(PRODUCT_URLS)
    out = OUTPUT_DIR / "review_api_discovery.json"
    out.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nCaptured {len(candidates)} candidate request(s) -> {out}")
    for c in candidates:
        print(f"  [{c['method']} {c['status']}] {c['url'][:120]}")


if __name__ == "__main__":
    main()
