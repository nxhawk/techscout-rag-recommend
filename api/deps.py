"""Dependencies - FastAPI dependency injection."""
from functools import lru_cache
from src.pipeline.config import PipelineConfig
from src.embedding.product_embedder import ProductEmbedder
from src.embedding.vector_store import VectorStore
from src.retrieval.product_retriever import ProductRetriever
from src.retrieval.filter_engine import FilterEngine
from src.retrieval.similarity_scorer import SimilarityScorer
from src.generation.llm_client import LLMClient
from src.pipeline.recommend.engine import RecommendEngine
from src.pipeline.recommend_pipeline import RecommendPipeline
from src.pipeline.compare.comparator import ProductComparator
from src.pipeline.compare_pipeline import ComparePipeline


@lru_cache()
def get_config() -> PipelineConfig:
    """Get pipeline configuration (cached)."""
    return PipelineConfig.from_yaml("configs/settings.yaml")


def get_embedder(config: PipelineConfig | None = None) -> ProductEmbedder:
    """Create and setup product embedder."""
    cfg = config or get_config()
    embedder = ProductEmbedder(
        model_name=cfg.embedding_model,
        provider=cfg.embedding_provider,
    )
    import os
    embedder.setup(api_key=os.getenv("OPENAI_API_KEY", ""))
    return embedder


def get_vector_store(config: PipelineConfig | None = None) -> VectorStore:
    """Create and setup vector store."""
    cfg = config or get_config()
    store = VectorStore(provider=cfg.vector_db, collection_name=cfg.collection_name)
    store.setup(persist_dir=cfg.vector_db_path)
    return store


def get_retriever(config: PipelineConfig | None = None) -> ProductRetriever:
    """Create product retriever with all dependencies."""
    cfg = config or get_config()
    return ProductRetriever(
        embedder=get_embedder(cfg),
        vector_store=get_vector_store(cfg),
        filter_engine=FilterEngine(),
        scorer=SimilarityScorer(),
    )


def get_llm_client(config: PipelineConfig | None = None) -> LLMClient:
    """Create and setup LLM client."""
    cfg = config or get_config()
    client = LLMClient(provider=cfg.llm_provider, model=cfg.llm_model)
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY", "") if cfg.llm_provider == "anthropic" else os.getenv("OPENAI_API_KEY", "")
    client.setup(api_key=api_key)
    return client


def get_recommend_pipeline(config: PipelineConfig | None = None) -> RecommendPipeline:
    """Create the full recommendation pipeline."""
    cfg = config or get_config()
    retriever = get_retriever(cfg)
    engine = RecommendEngine(retriever=retriever)
    llm = get_llm_client(cfg)
    return RecommendPipeline(recommend_engine=engine, llm_client=llm)


def get_compare_pipeline(config: PipelineConfig | None = None) -> ComparePipeline:
    """Create the full comparison pipeline."""
    cfg = config or get_config()
    retriever = get_retriever(cfg)
    comparator = ProductComparator()
    llm = get_llm_client(cfg)
    return ComparePipeline(retriever=retriever, comparator=comparator, llm_client=llm)
