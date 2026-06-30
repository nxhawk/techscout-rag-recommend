"""
Config - Cấu hình pipeline.
"""
import yaml
from pathlib import Path
from dataclasses import dataclass, field


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

    # Vector Store
    vector_db: str = "chroma"
    vector_db_path: str = "./data/embeddings"
    collection_name: str = "products"

    # Retrieval
    top_k_retrieve: int = 20
    top_k_recommend: int = 5
    top_k_compare: int = 3

    @classmethod
    def from_yaml(cls, filepath: str) -> "PipelineConfig":
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
