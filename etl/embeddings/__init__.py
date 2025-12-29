"""
Embedding services for generating vector representations of text.
"""

from .base import EmbeddingService
from .cohere_service import CohereEmbeddingService
from .vector_store import (
    VectorStore,
    SearchResult,
    IndexingResult,
    create_indexing_progress,
)

__all__ = [
    "EmbeddingService",
    "CohereEmbeddingService",
    "VectorStore",
    "SearchResult",
    "IndexingResult",
    "create_indexing_progress",
]