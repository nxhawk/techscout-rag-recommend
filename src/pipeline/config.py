"""
Config - Cấu hình pipeline.
"""

from dataclasses import dataclass

import yaml

from src.constants import (
    DEFAULT_COLLECTION_NAME,
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_ES_INDEX,
    DEFAULT_ES_URL,
    DEFAULT_LLM_MODEL,
    DEFAULT_POSTGRES_DSN,
    DEFAULT_RERANKER_MODEL,
)


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    # LLM
    llm_provider: str = "anthropic"
    llm_model: str = DEFAULT_LLM_MODEL
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3

    # Embedding
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Vector Store (Postgres + pgvector)
    vector_db: str = "pgvector"
    vector_db_url: str = DEFAULT_POSTGRES_DSN
    embedding_dim: int = DEFAULT_EMBEDDING_DIM
    collection_name: str = DEFAULT_COLLECTION_NAME

    # Retrieval
    top_k_retrieve: int = 20
    top_k_recommend: int = 5
    top_k_compare: int = 3

    # Hybrid retrieval (BM25 + RRF) & reranking
    use_bm25: bool = True
    rrf_k: int = 60
    keyword_candidates: int = 50
    use_reranker: bool = False
    reranker_model: str = DEFAULT_RERANKER_MODEL

    # Query rewriting (normalize/typo-correct/expand/intent-aware). Cheap and
    # local (no extra API calls) so it defaults on. `query_rewrite_max_variants`
    # controls multi-query fan-out: each extra variant costs one more
    # embedding call, so it defaults to 1 (single query, current behavior).
    use_query_rewrite: bool = True
    query_rewrite_max_variants: int = 1

    # Keyword backend: "memory" (in-memory BM25 snapshot) or "elasticsearch"
    # (CDC-synced index, pre-filtered). Env overrides: KEYWORD_BACKEND,
    # ELASTICSEARCH_URL.
    keyword_backend: str = "memory"
    es_url: str = DEFAULT_ES_URL
    es_index: str = DEFAULT_ES_INDEX

    # CDC sync (Debezium -> Kafka -> workers). Env overrides:
    # KAFKA_BOOTSTRAP_SERVERS.
    kafka_bootstrap: str = "localhost:9092"
    products_topic: str = "ragshop.public.product_catalog"
    catalog_table: str = "product_catalog"

    @classmethod
    def from_yaml(cls, filepath: str) -> "PipelineConfig":
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
