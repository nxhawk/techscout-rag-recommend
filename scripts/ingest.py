"""Script: Ingest product data (bootstrap).

Writes three targets so a fresh system is immediately usable:

1. ``product_catalog`` table - the source of truth (what CDC captures).
2. pgvector - direct embed + upsert (no Kafka required).
3. Elasticsearch keyword index - bulk upsert (skipped when unreachable).

Chunk metadata carries ``content_hash``, so when the CDC stack later replays
the Debezium initial snapshot of the catalog, the embedding worker detects
the vectors are already current and makes zero embedding API calls.

With ``--catalog-only`` the script writes only the catalog table and lets
the CDC pipeline (Debezium snapshot -> workers) build both indexes.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.catalog.product_repository import ProductRepository
from src.ingestion.product_loader import ProductLoader
from src.ingestion.data_cleaner import DataCleaner
from src.ingestion.chunker import ProductChunker
from src.embedding.product_embedder import ProductEmbedder
from src.embedding.vector_store import VectorStore
from src.pipeline.config import PipelineConfig
from src.sync.chunk_builder import build_chunk_payload
from src.utils.helpers import resolve_api_keys
from src.utils.logger import setup_logger

logger = setup_logger("ingest")


def _load_raw_products(source: str) -> list[dict]:
    loader = ProductLoader()
    if source == "crawled":
        return loader.load_crawled()
    if source == "products":
        return loader.load_all()
    return loader.load_all() + loader.load_crawled()


def _index_elasticsearch(config: PipelineConfig, ids, texts, metadatas) -> None:
    """Bulk-index chunks into ES; a missing cluster is not fatal (workers
    will build the index from the Debezium snapshot instead)."""
    if (os.getenv("KEYWORD_BACKEND") or config.keyword_backend).lower() != "elasticsearch":
        return
    from src.retrieval.es_keyword_search import ESKeywordSearch

    try:
        es = ESKeywordSearch(
            url=os.getenv("ELASTICSEARCH_URL") or config.es_url,
            index_name=config.es_index,
        )
        es.setup()
        indexed = es.upsert_chunks(ids, texts, metadatas)
        es.refresh()
        logger.info(f"Indexed {indexed} chunks into Elasticsearch")
    except Exception as exc:
        logger.warning(
            f"Elasticsearch indexing skipped ({exc}) - "
            "the CDC sync workers will build the index from the snapshot."
        )


def main():
    # Load environment variables from .env before any os.getenv lookups.
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Ingest product data into catalog + search indexes."
    )
    parser.add_argument(
        "--source",
        choices=["crawled", "products", "all"],
        default="crawled",
        help=(
            "Where to read products from: 'crawled' (data/raw/crawled/*/latest.json), "
            "'products' (data/raw/products), or 'all' (both). Default: crawled."
        ),
    )
    parser.add_argument(
        "--catalog-only",
        action="store_true",
        help=(
            "Write only the product_catalog table (source of truth) and let "
            "the CDC pipeline build the search indexes from the snapshot."
        ),
    )
    args = parser.parse_args()

    config = PipelineConfig.from_yaml("configs/settings.yaml")
    dsn = os.getenv("DATABASE_URL") or config.vector_db_url

    logger.info(f"Loading products (source={args.source})...")
    raw_products = _load_raw_products(args.source)
    logger.info(f"Loaded {len(raw_products)} products")

    cleaner = DataCleaner()
    profiles = [cleaner.build_product_profile(raw) for raw in raw_products]

    # 1. Source of truth first - everything else derives from this table.
    repo = ProductRepository(table_name=config.catalog_table)
    repo.setup(dsn=dsn)
    repo.upsert_many(profiles)
    logger.info(f"Upserted {len(profiles)} products into {config.catalog_table}")

    if args.catalog_only:
        logger.info("--catalog-only: CDC workers will build the search indexes.")
        return

    # 2. Chunk once, reuse for both indexes (same payload the workers build).
    chunker = ProductChunker()
    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict] = []
    for profile in profiles:
        chunk_ids, chunk_texts, chunk_metas = build_chunk_payload(profile, chunker)
        ids.extend(chunk_ids)
        texts.extend(chunk_texts)
        metadatas.extend(chunk_metas)
    logger.info(f"Created {len(ids)} chunks, embedding...")

    embedder = ProductEmbedder(
        model_name=config.embedding_model,
        provider=config.embedding_provider,
        embedding_dim=config.embedding_dim,
    )
    key_env = ProductEmbedder.PROVIDER_API_KEY_ENV.get(
        config.embedding_provider, "OPENAI_API_KEY"
    )
    embedder.setup(api_key=resolve_api_keys(key_env) or [""])

    store = VectorStore(
        collection_name=config.collection_name,
        embedding_dim=config.embedding_dim,
    )
    store.setup(dsn=dsn)

    embeddings = embedder.embed_batch(texts)
    store.add_documents(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    logger.info(f"Upserted {len(ids)} chunks into pgvector")

    # 3. Keyword index (optional - workers can also build it via CDC).
    _index_elasticsearch(config, ids, texts, metadatas)
    logger.info("Ingestion complete!")


if __name__ == "__main__":
    main()
