"""Script: Run a CDC sync worker (Debezium topic -> derived index).

Roles:
    indexer  - keep the Elasticsearch keyword index fresh
    embedder - keep the pgvector semantic index fresh

Usage:
    uv run python scripts/sync_worker.py --role indexer
    uv run python scripts/sync_worker.py --role embedder
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline.config import PipelineConfig
from src.sync.runner import build_consumer, run_loop
from src.utils.logger import setup_logger

logger = setup_logger("sync_worker")


def _build_indexer(config: PipelineConfig):
    from src.retrieval.es_keyword_search import ESKeywordSearch
    from src.sync.indexer_worker import SearchIndexer

    es = ESKeywordSearch(
        url=os.getenv("ELASTICSEARCH_URL") or config.es_url,
        index_name=config.es_index,
    )
    es.setup()
    return SearchIndexer(es)


def _build_embedder(config: PipelineConfig):
    from src.embedding.product_embedder import ProductEmbedder
    from src.embedding.vector_store import VectorStore
    from src.sync.embedding_worker import EmbeddingSyncer
    from src.utils.helpers import resolve_api_keys

    embedder = ProductEmbedder(
        model_name=config.embedding_model,
        provider=config.embedding_provider,
        embedding_dim=config.embedding_dim,
    )
    key_env = ProductEmbedder.PROVIDER_API_KEY_ENV.get(config.embedding_provider, "OPENAI_API_KEY")
    embedder.setup(api_key=resolve_api_keys(key_env) or [""])

    store = VectorStore(
        collection_name=config.collection_name,
        embedding_dim=config.embedding_dim,
    )
    store.setup(dsn=os.getenv("DATABASE_URL") or config.vector_db_url)
    return EmbeddingSyncer(embedder, store)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run a CDC sync worker.")
    parser.add_argument(
        "--role",
        choices=["indexer", "embedder"],
        required=True,
        help="indexer: Debezium topic -> Elasticsearch; embedder: Debezium topic -> pgvector",
    )
    args = parser.parse_args()

    config = PipelineConfig.from_yaml("configs/settings.yaml")
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS") or config.kafka_bootstrap

    handler = _build_indexer(config) if args.role == "indexer" else _build_embedder(config)
    consumer = build_consumer(
        bootstrap_servers=bootstrap,
        group_id=f"rag-sync-{args.role}",
        topic=config.products_topic,
    )
    logger.info(
        "Sync worker '%s' consuming %s from %s",
        args.role,
        config.products_topic,
        bootstrap,
    )
    run_loop(consumer, handler)


if __name__ == "__main__":
    main()
