"""
Cohere embedding service implementation.
"""

import os
from typing import List, Optional

import cohere

from .base import EmbeddingService


class CohereEmbeddingService(EmbeddingService):
    """
    Embedding service using Cohere API.
    
    Uses embed-english-v3.0 model (1024 dimensions).
    """
    
    MODEL = "embed-english-v3.0"
    DIMENSIONS = 1024
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Cohere service.
        
        Args:
            api_key: Cohere API key (defaults to COHERE_API_KEY env var)
        """
        self._api_key = api_key or os.environ.get("COHERE_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Cohere API key required. Set COHERE_API_KEY env var or pass api_key."
            )
        
        self._client = cohere.Client(self._api_key)
    
    @property
    def model_name(self) -> str:
        return self.MODEL
    
    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS
    
    async def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        response = self._client.embed(
            texts=[text],
            model=self.MODEL,
            input_type="search_query",
        )
        return response.embeddings[0]
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts (max 96 per call)."""
        response = self._client.embed(
            texts=texts,
            model=self.MODEL,
            input_type="search_document",
        )
        return response.embeddings