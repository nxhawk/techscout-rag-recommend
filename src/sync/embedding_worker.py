"""
Embedding Syncer - CDC consumer keeping pgvector fresh (S3).

The expensive path (embedding API call) runs ONLY when a text-bearing field
changed. Price/rating changes flow through a cheap metadata-only update, and
snapshot replays are skipped via the stored content hash - so replaying the
whole topic costs zero embedding calls when nothing changed.
"""

import logging

from src.embedding.product_embedder import ProductEmbedder
from src.embedding.vector_store import VectorStore
from src.ingestion.chunker import ProductChunker
from src.sync.chunk_builder import build_chunk_payload
from src.sync.events import ChangeEvent, content_hash, metadata_fields, text_changed

logger = logging.getLogger(__name__)


class EmbeddingSyncer:
    """Apply catalog change events to the pgvector semantic index."""

    def __init__(
        self,
        embedder: ProductEmbedder,
        vector_store: VectorStore,
        chunker: ProductChunker | None = None,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.chunker = chunker or ProductChunker()

    def handle(self, event: ChangeEvent) -> str:
        """Apply one event. Returns the action taken (for logs/tests)."""
        product_id = event.product_id
        if event.op == "d":
            deleted = self.vector_store.delete_product(product_id)
            logger.info("pgvector: deleted product %s (%d chunks)", product_id, deleted)
            return "deleted"

        if not self._needs_reembed(event):
            fields = metadata_fields(event.after)
            updated = self.vector_store.update_product_metadata(product_id, fields)
            logger.info(
                "pgvector: metadata-only update for %s (%d chunks, no embed call)",
                product_id,
                updated,
            )
            return "metadata"

        ids, documents, metadatas = build_chunk_payload(event.after, self.chunker)
        embeddings = self.embedder.embed_batch(documents)
        # Delete first so chunk types that disappeared don't linger.
        self.vector_store.delete_product(product_id)
        self.vector_store.add_documents(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
        logger.info("pgvector: re-embedded product %s (%d chunks)", product_id, len(ids))
        return "embedded"

    def _needs_reembed(self, event: ChangeEvent) -> bool:
        """Decide between the expensive embed path and metadata-only.

        1. Updates with a full before-image (REPLICA IDENTITY FULL): compare
           the text-bearing fields directly.
        2. Creates, snapshot reads, or missing before-image: compare the
           content hash against what the vector store already has - snapshot
           replays of unchanged products cost no embedding call.
        """
        if event.op == "u" and event.before is not None:
            return text_changed(event.before, event.after)
        stored = self.vector_store.get_product_content_hash(event.product_id)
        return stored is None or stored != content_hash(event.after)
