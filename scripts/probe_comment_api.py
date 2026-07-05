"""Probe the CellphoneS comment GraphQL API for a starred-review query type.

The verified COMMENTS query (`type: "product"`) returns the Q&A/comment feed.
The PDP also shows a starred "Đánh giá & nhận xét" feed whose query we have
not captured yet. This utility POSTs a handful of query variations and stores
the raw responses; GraphQL error messages ("Cannot query field X... Did you
mean Y?") double as schema discovery.

Usage (requires network access to api.cellphones.com.vn):
    uv run python scripts/probe_comment_api.py

Output: data/raw/crawled/probe_results.json
"""
import json
from pathlib import Path

import httpx

API = "https://api.cellphones.com.vn/graphql-customer/graphql/query"
PAGE_URL = "https://cellphones.com.vn/iphone-16-pro-max.html"
PRODUCT_ID = 59258
OUTPUT_PATH = Path("data/raw/crawled/probe_results.json")

HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://cellphones.com.vn",
    "Referer": "https://cellphones.com.vn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}

_BASE_FIELDS = "id content is_shown is_admin created_at customer { fullname }"


def comment_query(query_type: str, fields: str) -> str:
    """Build a COMMENTS query for a given `type` argument and match fields."""
    return (
        "query COMMENTS { comment("
        f'type: "{query_type}", pageUrl: "{PAGE_URL}", '
        f"productId: {PRODUCT_ID}, currentPage: 1"
        ") { total matches { " + fields + " } } }"
    )


# name -> GraphQL query. Field-discovery probes intentionally ask for fields
# that may not exist: the error text reveals the real field names.
PROBES: dict[str, str] = {
    "type_product_baseline": comment_query("product", _BASE_FIELDS),
    "type_rating": comment_query("rating", _BASE_FIELDS),
    "type_review": comment_query("review", _BASE_FIELDS),
    "field_discovery_rating": comment_query(
        "product", _BASE_FIELDS + " rating star point score is_rating rating_value"
    ),
    "root_field_discovery": (
        'query R { rating(productId: %d, currentPage: 1) { total } }' % PRODUCT_ID
    ),
    "root_field_discovery2": (
        'query R { review(productId: %d, currentPage: 1) { total } }' % PRODUCT_ID
    ),
}


def main() -> None:
    results: dict[str, dict] = {}
    with httpx.Client(headers=HEADERS, timeout=20.0) as client:
        for name, query in PROBES.items():
            try:
                resp = client.post(API, json={"query": query, "variables": {}})
                body = resp.text[:6000]
                results[name] = {"status": resp.status_code, "body": body}
                summary = body[:140].replace("\n", " ")
                print(f"[{resp.status_code}] {name}: {summary}")
            except httpx.HTTPError as exc:
                results[name] = {"status": -1, "body": str(exc)}
                print(f"[ERR] {name}: {exc}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nSaved -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
