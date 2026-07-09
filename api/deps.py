"""Dependencies - FastAPI dependency injection."""

import logging
import os
import re
import time
from functools import lru_cache
from src.utils.helpers import resolve_api_keys
from src.catalog.product_repository import ProductRepository
from src.pipeline.config import PipelineConfig
from src.embedding.product_embedder import ProductEmbedder
from src.embedding.vector_store import VectorStore
from src.retrieval.product_retriever import ProductRetriever
from src.retrieval.es_keyword_search import ESKeywordSearch
from src.retrieval.filter_engine import FilterEngine
from src.retrieval.hybrid_search import HybridSearch
from src.retrieval.query_rewriter import QueryRewriter
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.similarity_scorer import SimilarityScorer
from src.generation.llm_client import LLMClient
from src.pipeline.recommend.engine import RecommendEngine
from src.pipeline.recommend_pipeline import RecommendPipeline
from src.pipeline.compare.comparator import ProductComparator
from src.pipeline.compare_pipeline import ComparePipeline
from api.paths import SETTINGS_PATH

logger = logging.getLogger(__name__)


def _mask_dsn(dsn: str) -> str:
    """Hide the password portion of a connection string for safe logging."""
    return re.sub(r"//([^:/@]+):[^@]+@", r"//\1:***@", dsn)


@lru_cache()
def get_config() -> PipelineConfig:
    """Get pipeline configuration (cached)."""
    return PipelineConfig.from_yaml(str(SETTINGS_PATH))


def get_embedder(config: PipelineConfig | None = None) -> ProductEmbedder:
    """Create and setup product embedder."""
    cfg = config or get_config()
    # max_retries=0: in the API path a rate-limited provider must fail fast
    # (503) instead of sleeping through quota-wait cycles (up to ~60s each,
    # which makes requests appear to hang). Key rotation still applies.
    # Batch scripts (scripts/ingest.py) build their own clients and keep the
    # patient defaults.
    embedder = ProductEmbedder(
        model_name=cfg.embedding_model,
        provider=cfg.embedding_provider,
        embedding_dim=cfg.embedding_dim,
        max_retries=0,
    )
    env_var = ProductEmbedder.PROVIDER_API_KEY_ENV.get(cfg.embedding_provider, "OPENAI_API_KEY")
    keys = resolve_api_keys(env_var)
    if keys:
        logger.info(
            "Embedder ready: provider=%s model=%s (%d API key(s) from %s)",
            cfg.embedding_provider,
            cfg.embedding_model,
            len(keys),
            env_var,
        )
    else:
        logger.warning(
            "No API key found in env var %s - embedding calls WILL fail. "
            "Set it in .env and restart.",
            env_var,
        )
    embedder.setup(api_key=keys or [""])
    return embedder


def get_vector_store(config: PipelineConfig | None = None) -> VectorStore:
    """Create and setup vector store."""
    cfg = config or get_config()
    store = VectorStore(
        provider=cfg.vector_db,
        collection_name=cfg.collection_name,
        embedding_dim=cfg.embedding_dim,
    )
    logger.info(
        "Connecting to vector store %s (table=%s, dim=%s)",
        _mask_dsn(cfg.vector_db_url),
        cfg.collection_name,
        cfg.embedding_dim,
    )
    store.setup(dsn=cfg.vector_db_url)
    logger.info("Vector store connected")
    return store


def get_query_rewriter(config: PipelineConfig | None = None) -> QueryRewriter | None:
    """Create the query rewriter if enabled.

    Returns None when ``use_query_rewrite`` is off, so ``ProductRetriever``
    transparently skips the rewrite step (mirrors ``get_reranker``).
    """
    cfg = config or get_config()
    if not cfg.use_query_rewrite:
        return None
    return QueryRewriter(max_variants=cfg.query_rewrite_max_variants)


def get_retriever(config: PipelineConfig | None = None) -> ProductRetriever:
    """Create product retriever with all dependencies."""
    cfg = config or get_config()
    return ProductRetriever(
        embedder=get_embedder(cfg),
        vector_store=get_vector_store(cfg),
        filter_engine=FilterEngine(),
        scorer=SimilarityScorer(),
        query_rewriter=get_query_rewriter(cfg),
    )


def get_keyword_backend(config: PipelineConfig | None = None) -> ESKeywordSearch | None:
    """Create the Elasticsearch keyword backend if configured and reachable.

    Returns None when ``keyword_backend`` is not "elasticsearch" or the
    cluster is down, so callers can fall back to the in-memory BM25 snapshot.
    """
    cfg = config or get_config()
    backend_name = (os.getenv("KEYWORD_BACKEND") or cfg.keyword_backend).lower()
    if backend_name != "elasticsearch":
        return None
    url = os.getenv("ELASTICSEARCH_URL") or cfg.es_url
    backend = ESKeywordSearch(url=url, index_name=cfg.es_index)
    try:
        backend.setup()
    except Exception as exc:
        logger.warning(
            "Elasticsearch unavailable at %s (%s) - falling back to in-memory BM25",
            url,
            exc,
        )
        return None
    logger.info("Keyword backend: Elasticsearch at %s (index=%s)", url, cfg.es_index)
    return backend


def get_searcher(config: PipelineConfig | None = None) -> ProductRetriever | HybridSearch:
    """Create the retrieval component for the recommend flow.

    With ``use_bm25`` enabled, wraps the ProductRetriever in HybridSearch
    (semantic + keyword fused with RRF). Keyword backend preference:

    1. Elasticsearch (``keyword_backend: elasticsearch``) - CDC-synced,
       filters pre-applied in the query, shared across API workers.
    2. In-memory BM25 snapshot - built once at startup from the vector store.
    3. Semantic-only - if the snapshot build fails too (e.g. empty store).
    """
    cfg = config or get_config()
    retriever = get_retriever(cfg)
    if not cfg.use_bm25:
        return retriever

    es_backend = get_keyword_backend(cfg)
    searcher = HybridSearch(
        retriever,
        bm25_index=es_backend,  # None -> HybridSearch creates a BM25Index
        rrf_k=cfg.rrf_k,
        keyword_candidates=cfg.keyword_candidates,
    )
    if es_backend is not None:
        return searcher
    try:
        searcher.setup()
    except Exception as exc:
        logger.warning(
            "BM25 index build failed (%s) - falling back to semantic-only retrieval",
            exc,
        )
        return retriever
    return searcher


@lru_cache()
def get_cached_product_repository() -> ProductRepository:
    """Cached repository for the product CRUD routes (source of truth).

    CRUD writes go ONLY to the ``product_catalog`` table; Debezium (CDC)
    propagates changes to Elasticsearch and pgvector via the sync workers.
    """
    cfg = get_config()
    repo = ProductRepository(table_name=cfg.catalog_table)
    dsn = os.getenv("DATABASE_URL") or cfg.vector_db_url
    repo.setup(dsn=dsn)
    logger.info("Product repository ready (table=%s)", cfg.catalog_table)
    return repo


def get_reranker(config: PipelineConfig | None = None) -> CrossEncoderReranker | None:
    """Create the cross-encoder reranker if enabled and installed.

    Returns None when ``use_reranker`` is off or sentence-transformers is
    missing, so the engine transparently skips the reranking step.
    """
    cfg = config or get_config()
    if not cfg.use_reranker:
        return None
    reranker = CrossEncoderReranker(model_name=cfg.reranker_model)
    try:
        reranker.setup()
    except ImportError as exc:
        logger.warning("Reranker disabled: %s", exc)
        return None
    logger.info("Cross-encoder reranker ready: %s", cfg.reranker_model)
    return reranker


def get_llm_client(config: PipelineConfig | None = None) -> LLMClient:
    """Create and setup LLM client."""
    cfg = config or get_config()
    # max_retries=0: fail fast on quota errors in the API path (see get_embedder).
    client = LLMClient(provider=cfg.llm_provider, model=cfg.llm_model, max_retries=0)
    env_var = LLMClient.PROVIDER_API_KEY_ENV.get(cfg.llm_provider, "")
    keys = resolve_api_keys(env_var)
    if keys:
        logger.info(
            "LLM client ready: provider=%s model=%s (%d API key(s) from %s)",
            cfg.llm_provider,
            cfg.llm_model,
            len(keys),
            env_var,
        )
    else:
        logger.warning(
            "No API key found in env var %s - LLM calls WILL fail. Set it in .env and restart.",
            env_var,
        )
    client.setup(api_key=keys or [""])
    return client


def get_recommend_pipeline(config: PipelineConfig | None = None) -> RecommendPipeline:
    """Create the full recommendation pipeline."""
    cfg = config or get_config()
    searcher = get_searcher(cfg)
    engine = RecommendEngine(retriever=searcher, reranker=get_reranker(cfg))
    llm = get_llm_client(cfg)
    return RecommendPipeline(recommend_engine=engine, llm_client=llm)


@lru_cache()
def get_cached_recommend_pipeline() -> RecommendPipeline:
    """Cached, zero-arg recommend pipeline provider for FastAPI Depends().

    Building the pipeline is expensive (embedder setup, vector DB
    connection, LLM client setup), so it is created once and reused.
    """
    logger.info("Building recommend pipeline (first request only)...")
    t0 = time.perf_counter()
    pipeline = get_recommend_pipeline()
    logger.info("Recommend pipeline built in %.2fs", time.perf_counter() - t0)
    return pipeline


def get_compare_pipeline(config: PipelineConfig | None = None) -> ComparePipeline:
    """Create the full comparison pipeline."""
    cfg = config or get_config()
    retriever = get_retriever(cfg)
    comparator = ProductComparator()
    llm = get_llm_client(cfg)
    return ComparePipeline(
        retriever=retriever,
        comparator=comparator,
        llm_client=llm,
        product_repository=get_cached_product_repository(),
    )


@lru_cache()
def get_cached_compare_pipeline() -> ComparePipeline:
    """Cached, zero-arg compare pipeline provider for FastAPI Depends().

    Mirrors ``get_cached_recommend_pipeline``: building the pipeline is
    expensive (embedder setup, vector DB connection, LLM client setup), so
    it is created once and reused.
    """
    logger.info("Building compare pipeline (first request only)...")
    t0 = time.perf_counter()
    pipeline = get_compare_pipeline()
    logger.info("Compare pipeline built in %.2fs", time.perf_counter() - t0)
    return pipeline
