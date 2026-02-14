"""
Abstract base class for embedding services.
"""

from abc import ABC, abstractmethod
from typing import List


class EmbeddingService(ABC):
    """Abstract embedding service interface."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the embedding model."""
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensionality of embeddings."""
        pass

    @abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query text."""
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts."""
        pass