"""
Elasticsearch Keyword Search - BM25 keyword branch backed by an ES index.

Replaces the in-memory :class:`BM25Index` snapshot in production: the index
is kept fresh by the CDC sync workers (``src/sync/``), it is shared by all
API workers, and the extracted filters are pushed down as ``bool.filter``
clauses so the keyword branch PRE-filters (same guarantee as the SQL WHERE
on the semantic branch) instead of post-filtering in Python.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ES_URL = "http://localhost:9200"

# Standard tokenizer + lowercase keeps Vietnamese diacritics intact,
# mirroring the in-memory tokenizer (``\w+`` on lowercased text).
_INDEX_SETTINGS = {
    "analysis": {
        "normalizer": {"lowercase_normalizer": {"type": "custom", "filter": ["lowercase"]}}
    }
}
_INDEX_MAPPINGS = {
    "properties": {
        "document": {"type": "text"},
        "name": {"type": "text"},
        "product_id": {"type": "keyword"},
        "chunk_type": {"type": "keyword"},
        "brand": {"type": "keyword", "normalizer": "lowercase_normalizer"},
        "category": {"type": "keyword", "normalizer": "lowercase_normalizer"},
        "price": {"type": "double"},
        "avg_rating": {"type": "float"},
        "content_hash": {"type": "keyword"},
    }
}


def build_bool_query(query: str, filters: dict[str, Any] | None) -> dict:
    """Build the ES bool query: BM25 match + filters as PRE-filter clauses.

    Mirrors ``ProductRetriever._build_where_clause`` on the semantic branch so
    both branches enforce the same constraint set at query time.
    """
    filters = filters or {}
    filter_clauses: list[dict] = []
    if filters.get("brand"):
        filter_clauses.append({"term": {"brand": str(filters["brand"]).lower()}})
    if filters.get("category"):
        filter_clauses.append({"term": {"category": str(filters["category"]).lower()}})
    price_range: dict[str, Any] = {}
    if "price_min" in filters:
        price_range["gte"] = filters["price_min"]
    if "price_max" in filters:
        price_range["lte"] = filters["price_max"]
    if price_range:
        filter_clauses.append({"range": {"price": price_range}})
    if "min_rating" in filters:
        filter_clauses.append({"range": {"avg_rating": {"gte": filters["min_rating"]}}})
    return {
        "bool": {
            "must": [{"match": {"document": {"query": query}}}],
            "filter": filter_clauses,
        }
    }


class ESKeywordSearch:
    """Keyword search over product chunks stored in Elasticsearch.

    Drop-in keyword backend for :class:`HybridSearch`. ``prefilters = True``
    tells HybridSearch that filters are applied inside the query (no Python
    post-filtering needed).
    """

    prefilters = True

    def __init__(
        self,
        url: str = DEFAULT_ES_URL,
        index_name: str = "product_chunks",
        timeout: float = 5.0,
    ):
        self.url = url
        self.index_name = index_name
        self.timeout = timeout
        self.client = None

    def setup(self) -> None:
        """Connect and create the index (idempotent). Raises if unreachable."""
        from elasticsearch import Elasticsearch

        self.client = Elasticsearch(self.url, request_timeout=self.timeout)
        if not self.client.ping():
            raise ConnectionError(f"Elasticsearch not reachable at {self.url}")
        if not self.client.indices.exists(index=self.index_name):
            self.client.indices.create(
                index=self.index_name,
                settings=_INDEX_SETTINGS,
                mappings=_INDEX_MAPPINGS,
            )
            logger.info("Created ES index %s", self.index_name)

    def ping(self) -> bool:
        """True when the cluster is reachable."""
        try:
            return bool(self.client is not None and self.client.ping())
        except Exception:
            return False

    # ---------------------------------------------------------------- search

    def search(
        self,
        query: str,
        top_k: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[dict]:
        """BM25 search with filters pushed down as bool.filter (pre-filter).

        Returns candidates shaped exactly like ``BM25Index.search``:
        ``{"id", "document", "metadata", "bm25_score"}``.
        """
        response = self.client.search(
            index=self.index_name,
            query=build_bool_query(query, filters),
            size=top_k,
        )
        results = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            results.append(
                {
                    "id": hit["_id"],
                    "document": source.get("document", ""),
                    "metadata": {k: v for k, v in source.items() if k != "document"},
                    "bm25_score": float(hit["_score"] or 0.0),
                }
            )
        return results

    # -------------------------------------------------------------- indexing

    def upsert_chunks(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
    ) -> int:
        """Bulk-upsert chunk documents (idempotent by chunk id)."""
        from elasticsearch import helpers

        actions = [
            {
                "_op_type": "index",
                "_index": self.index_name,
                "_id": chunk_id,
                "_source": {"document": document, **metadata},
            }
            for chunk_id, document, metadata in zip(ids, documents, metadatas)
        ]
        success, _ = helpers.bulk(self.client, actions, refresh=False)
        return int(success)

    def delete_product(self, product_id: str) -> int:
        """Delete every chunk of a product. Returns docs deleted."""
        response = self.client.delete_by_query(
            index=self.index_name,
            query={"term": {"product_id": product_id}},
            refresh=True,
            conflicts="proceed",
        )
        return int(response.get("deleted", 0))

    def refresh(self) -> None:
        """Make recent writes searchable immediately (tests / bootstrap)."""
        self.client.indices.refresh(index=self.index_name)

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
