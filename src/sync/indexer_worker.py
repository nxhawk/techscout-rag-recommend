"""
Search Indexer - CDC consumer keeping the Elasticsearch index fresh (S2).

Idempotent by construction: chunk ids are deterministic
(``{product_id}_{chunk_type}``) and every apply is an upsert/delete, so
replaying the stream (snapshot restarts, consumer rebalances) converges to
the same index state.
"""

import logging

from src.ingestion.chunker import ProductChunker
from src.retrieval.es_keyword_search import ESKeywordSearch
from src.sync.chunk_builder import build_chunk_payload
from src.sync.events import ChangeEvent

logger = logging.getLogger(__name__)


class SearchIndexer:
    """Apply catalog change events to the Elasticsearch keyword index."""

    def __init__(self, es: ESKeywordSearch, chunker: ProductChunker | None = None):
        self.es = es
        self.chunker = chunker or ProductChunker()

    def handle(self, event: ChangeEvent) -> str:
        """Apply one event. Returns the action taken (for logs/tests)."""
        product_id = event.product_id
        if event.op == "d":
            deleted = self.es.delete_product(product_id)
            logger.info("ES: deleted product %s (%d chunks)", product_id, deleted)
            return "deleted"

        # c / u / r -> rebuild the product's chunk set. Delete first so chunk
        # types that disappeared (e.g. specs removed) don't linger.
        ids, documents, metadatas = build_chunk_payload(event.after, self.chunker)
        self.es.delete_product(product_id)
        self.es.upsert_chunks(ids, documents, metadatas)
        logger.info("ES: upserted product %s (%d chunks)", product_id, len(ids))
        return "upserted"
