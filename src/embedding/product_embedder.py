"""
Product Embedder - Tạo embeddings cho product chunks.
"""
from typing import Optional


class ProductEmbedder:
    """Generate embeddings for product chunks."""

    def __init__(self, model_name: str = "text-embedding-3-small", provider: str = "openai"):
        self.model_name = model_name
        self.provider = provider
        self.client = None  # Initialize in setup()

    def setup(self, api_key: str) -> None:
        """Initialize embedding client."""
        if self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        if self.provider == "openai":
            response = self.client.embeddings.create(
                model=self.model_name,
                input=text,
            )
            return response.data[0].embedding
        raise ValueError(f"Unsupported provider: {self.provider}")

    def embed_batch(self, texts: list[str], batch_size: int = 100) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            if self.provider == "openai":
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=batch,
                )
                all_embeddings.extend([d.embedding for d in response.data])
        return all_embeddings
