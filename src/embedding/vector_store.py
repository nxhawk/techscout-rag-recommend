"""
Vector Store - Quản lý kết nối và thao tác với Vector Database.
Hỗ trợ: ChromaDB (dev), Qdrant (prod).
"""
from typing import Any, Optional


class VectorStore:
    """Manage vector database operations."""

    def __init__(self, provider: str = "chroma", collection_name: str = "products"):
        self.provider = provider
        self.collection_name = collection_name
        self.collection = None

    def setup(self, **kwargs) -> None:
        """Initialize vector database connection."""
        if self.provider == "chroma":
            import chromadb
            persist_dir = kwargs.get("persist_dir", "./data/embeddings")
            self.client = chromadb.PersistentClient(path=persist_dir)
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )

    def add_documents(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Add documents with embeddings to the store."""
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: Optional[dict] = None,
    ) -> dict:
        """Query similar documents."""
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    def delete_collection(self) -> None:
        """Delete the current collection."""
        self.client.delete_collection(self.collection_name)
