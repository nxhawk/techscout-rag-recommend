"""
Chunk Builder - Turn a catalog row into index-ready chunk payloads.

Shared by both sync workers and the bootstrap ingest script so Elasticsearch
and pgvector always contain identically shaped chunk documents
(``id = {product_id}_{chunk_type}``, metadata = chunk fields minus text).
"""

from src.ingestion.chunker import ProductChunker
from src.sync.events import content_hash


def build_chunk_payload(
    product: dict,
    chunker: ProductChunker | None = None,
) -> tuple[list[str], list[str], list[dict]]:
    """Chunk a product row into (ids, documents, metadatas).

    Metadata carries ``content_hash`` (hash of the text-bearing fields) so
    snapshot replays can detect that re-embedding is unnecessary.
    """
    chunker = chunker or ProductChunker()
    chunks = chunker.chunk_product(product)
    product_hash = content_hash(product)

    ids = [f"{chunk['product_id']}_{chunk['chunk_type']}" for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [
        {**{k: v for k, v in chunk.items() if k != "text"}, "content_hash": product_hash}
        for chunk in chunks
    ]
    return ids, documents, metadatas
