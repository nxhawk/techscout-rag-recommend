"""
Config - Cấu hình pipeline.
"""
import yaml
from dataclasses import dataclass


@dataclass
class PipelineConfig:
    """Pipeline configuration."""
    # LLM
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.3

    # Embedding
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"

    # Vector Store (Postgres + pgvector)
    vector_db: str = "pgvector"
    vector_db_url: str = "postgresql://postgres:postgres@localhost:5432/rag_products"
    embedding_dim: int = 1536
    collection_name: str = "products"

    # Retrieval
    top_k_retrieve: int = 20
    top_k_recommend: int = 5
    top_k_compare: int = 3

    # Hybrid retrieval (BM25 + RRF) & reranking
    use_bm25: bool = True
    rrf_k: int = 60
    keyword_candidates: int = 50
    use_reranker: bool = False
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # Keyword backend: "memory" (in-memory BM25 snapshot) or "elasticsearch"
    # (CDC-synced index, pre-filtered). Env overrides: KEYWORD_BACKEND,
    # ELASTICSEARCH_URL.
    keyword_backend: str = "memory"
    es_url: str = "http://localhost:9200"
    es_index: str = "product_chunks"

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
