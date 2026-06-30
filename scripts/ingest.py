"""Script: Ingest product data vao vector store."""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ingestion.product_loader import ProductLoader
from src.ingestion.data_cleaner import DataCleaner
from src.ingestion.chunker import ProductChunker
from src.embedding.product_embedder import ProductEmbedder
from src.embedding.vector_store import VectorStore
from src.pipeline.config import PipelineConfig
from src.utils.logger import setup_logger

logger = setup_logger("ingest")


def main():
    config = PipelineConfig.from_yaml("configs/settings.yaml")

    loader = ProductLoader()
    cleaner = DataCleaner()
    chunker = ProductChunker()

    embedder = ProductEmbedder(model_name=config.embedding_model)
    import os
    embedder.setup(api_key=os.getenv("OPENAI_API_KEY", ""))

    store = VectorStore(collection_name=config.collection_name)
    store.setup(persist_dir=config.vector_db_path)

    logger.info("Loading products...")
    raw_products = loader.load_all()
    logger.info(f"Loaded {len(raw_products)} products")

    all_chunks = []
    for raw in raw_products:
        product = cleaner.build_product_profile(raw)
        chunks = chunker.chunk_product(product)
        all_chunks.extend(chunks)

    logger.info(f"Created {len(all_chunks)} chunks, embedding...")

    texts = [c["text"] for c in all_chunks]
    embeddings = embedder.embed_batch(texts)

    ids = [f"{c['product_id']}_{c['chunk_type']}" for c in all_chunks]
    metadatas = [
        {k: v for k, v in c.items() if k != "text"}
        for c in all_chunks
    ]

    store.add_documents(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )
    logger.info("Ingestion complete!")


if __name__ == "__main__":
    main()
