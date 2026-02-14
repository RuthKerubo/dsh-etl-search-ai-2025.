"""
Cohere embedding service implementation.
"""

import os
import time
from typing import List, Optional

import cohere
from cohere.errors import TooManyRequestsError

from .base import EmbeddingService


class CohereEmbeddingService(EmbeddingService):
    """Embedding service using Cohere API."""

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("COHERE_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Cohere API key required. Set COHERE_API_KEY env var or pass api_key."
            )

        self._model = os.getenv("COHERE_EMBEDDING_MODEL", "embed-english-light-v3.0")

        # Dimensions depend on model
        if "light" in self._model:
            self._dimensions = 384
        else:
            self._dimensions = 1024

        self._client = cohere.Client(self._api_key)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_query(self, text: str, max_retries: int = 3) -> List[float]:
        """Embed a single query with retry logic."""
        for attempt in range(max_retries):
            try:
                response = self._client.embed(
                    texts=[text],
                    model=self._model,
                    input_type="search_query",
                )
                return response.embeddings[0]
            except TooManyRequestsError:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 30
                    print(f"⏳ Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise

    async def embed_batch(self, texts: List[str], max_retries: int = 3) -> List[List[float]]:
        """Embed a batch of texts with retry logic."""
        for attempt in range(max_retries):
            try:
                response = self._client.embed(
                    texts=texts,
                    model=self._model,
                    input_type="search_document",
                )
                return response.embeddings
            except TooManyRequestsError:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 30
                    print(f"⏳ Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise