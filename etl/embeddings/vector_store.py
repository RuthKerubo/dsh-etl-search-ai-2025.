"""
Vector Store with ChromaDB.

Stores embeddings and provides semantic search capabilities.
Integrates with the Cohere embedding service for generating embeddings.

Usage:
    from etl.embeddings import CohereEmbeddingService
    from etl.embeddings.vector_store import VectorStore

    embedding_service = CohereEmbeddingService(api_key="...")
    store = VectorStore(
        embedding_service=embedding_service,
        persist_path="./data/chroma",
    )

    # Add datasets
    await store.add_datasets(datasets)

    # Search
    results = await store.search("climate change rainfall")
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import chromadb
from chromadb.config import Settings

from etl.models.dataset import DatasetMetadata
from .base import EmbeddingService


@dataclass
class SearchResult:
    """A semantic search result."""
    dataset_id: str
    title: str
    abstract: str
    score: float  # Similarity score (0-1, higher is better)
    keywords: list[str] = field(default_factory=list)


@dataclass
class IndexingResult:
    """Result of indexing datasets."""
    successful: list[str] = field(default_factory=list)  # Dataset IDs
    failed: list[tuple[str, str]] = field(default_factory=list)  # (ID, error)

    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    api_calls: int = 0

    @property
    def total(self) -> int:
        return len(self.successful) + len(self.failed)

    @property
    def success_rate(self) -> float:
        return len(self.successful) / self.total if self.total > 0 else 0.0

    def summary(self) -> str:
        duration = (self.completed_at or datetime.utcnow()) - self.started_at
        return (
            f"Indexed {len(self.successful)}/{self.total} datasets "
            f"({self.success_rate:.1%}) in {duration.total_seconds():.1f}s"
        )


# Progress callback: (dataset_id, current, total) -> None
ProgressCallback = Callable[[str, int, int], None]


class VectorStore:
    """
    Vector store for semantic search using ChromaDB.

    Features:
    - Persistent storage
    - Semantic similarity search
    - Batch indexing with progress tracking
    - Metadata filtering

    Example:
        store = VectorStore(
            embedding_service=CohereEmbeddingService(),
            persist_path="./data/chroma",
        )

        # Index datasets
        result = await store.add_datasets(datasets)
        print(result.summary())

        # Search
        results = await store.search("drought conditions", limit=5)
        for r in results:
            print(f"{r.score:.3f} {r.title}")
    """

    COLLECTION_NAME = "datasets"

    def __init__(
        self,
        embedding_service: EmbeddingService,
        persist_path: str | Path = "./data/chroma",
        batch_size: int = 96,
        batch_delay: float = 1.0,
    ):
        """
        Initialize vector store.

        Args:
            embedding_service: Service for generating embeddings
            persist_path: Path for ChromaDB storage
            batch_size: Embeddings per API call
            batch_delay: Delay between batches (rate limiting)
        """
        self.embedding_service = embedding_service
        self.persist_path = Path(persist_path)
        self.batch_size = batch_size
        self.batch_delay = batch_delay

        # Ensure directory exists
        self.persist_path.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client
        self._client = chromadb.PersistentClient(
            path=str(self.persist_path),
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create collection
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # =========================================================================
    # Indexing
    # =========================================================================

    async def add_datasets(
        self,
        datasets: list[DatasetMetadata],
        skip_existing: bool = True,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> IndexingResult:
        """
        Add datasets to the vector store.

        Args:
            datasets: Datasets to index
            skip_existing: Skip already-indexed datasets
            progress_callback: Optional progress callback

        Returns:
            IndexingResult with success/failure details
        """
        result = IndexingResult()

        # Filter existing if requested
        if skip_existing:
            existing = set(self.get_indexed_ids())
            datasets = [d for d in datasets if d.identifier not in existing]

        if not datasets:
            result.completed_at = datetime.utcnow()
            return result

        total = len(datasets)

        # Process in batches
        for i in range(0, len(datasets), self.batch_size):
            batch = datasets[i:i + self.batch_size]

            try:
                # Prepare texts
                texts = [self._format_text(d) for d in batch]

                # Generate embeddings
                embeddings = await self.embedding_service.embed_batch(texts)
                result.api_calls += 1

                # Store in ChromaDB
                ids = [d.identifier for d in batch]
                metadatas = [self._create_metadata(d) for d in batch]

                self._collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    documents=texts,
                )

                # Record successes
                for d in batch:
                    result.successful.append(d.identifier)
                    if progress_callback:
                        progress_callback(
                            d.identifier,
                            len(result.successful) + len(result.failed),
                            total,
                        )

            except Exception as e:
                # Record failures
                for d in batch:
                    result.failed.append((d.identifier, str(e)))

            # Rate limiting
            if i + self.batch_size < len(datasets):
                await asyncio.sleep(self.batch_delay)

        result.completed_at = datetime.utcnow()
        return result

    async def add_single(self, dataset: DatasetMetadata) -> bool:
        """Add a single dataset. Returns True if successful."""
        result = await self.add_datasets([dataset], skip_existing=False)
        return len(result.successful) > 0

    async def update_dataset(self, dataset: DatasetMetadata) -> bool:
        """Update an existing dataset's embedding."""
        try:
            # Remove old
            self._collection.delete(ids=[dataset.identifier])

            # Add new
            return await self.add_single(dataset)
        except Exception:
            return False

    # =========================================================================
    # Search
    # =========================================================================

    async def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """
        Semantic search for datasets.

        Args:
            query: Search query
            limit: Maximum results
            min_score: Minimum similarity (0-1)

        Returns:
            List of SearchResult ordered by relevance
        """
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_query(query)

        # Search ChromaDB
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["metadatas", "documents", "distances"],
        )

        # Convert to SearchResult
        search_results = []

        if results["ids"] and results["ids"][0]:
            for i, dataset_id in enumerate(results["ids"][0]):
                # Convert distance to similarity (cosine: sim = 1 - dist)
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 - distance

                if score < min_score:
                    continue

                metadata = results["metadatas"][0][i] if results["metadatas"] else {}

                search_results.append(SearchResult(
                    dataset_id=dataset_id,
                    title=metadata.get("title", ""),
                    abstract=metadata.get("abstract", ""),
                    score=score,
                    keywords=metadata.get("keywords", "").split(",") if metadata.get("keywords") else [],
                ))

        return search_results

    async def search_with_keywords(
        self,
        query: str,
        keywords: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """
        Search with optional keyword filtering.

        Args:
            query: Semantic search query
            keywords: Required keywords (any match)
            limit: Maximum results

        Returns:
            Filtered search results
        """
        # Get more results for filtering
        results = await self.search(query, limit=limit * 3)

        if keywords:
            keywords_lower = {k.lower() for k in keywords}
            results = [
                r for r in results
                if any(k.lower() in keywords_lower for k in r.keywords)
            ]

        return results[:limit]

    # =========================================================================
    # Management
    # =========================================================================

    def get_stats(self) -> dict:
        """Get store statistics."""
        return {
            "total_documents": self._collection.count(),
            "collection_name": self.COLLECTION_NAME,
            "persist_path": str(self.persist_path),
            "embedding_model": self.embedding_service.model_name,
            "embedding_dimensions": self.embedding_service.dimensions,
        }

    def get_indexed_ids(self) -> list[str]:
        """Get all indexed dataset IDs."""
        result = self._collection.get()
        return result["ids"]

    def is_indexed(self, dataset_id: str) -> bool:
        """Check if dataset is indexed."""
        result = self._collection.get(ids=[dataset_id])
        return len(result["ids"]) > 0

    def delete(self, dataset_id: str) -> bool:
        """Delete a dataset from the store."""
        try:
            self._collection.delete(ids=[dataset_id])
            return True
        except Exception:
            return False

    def clear(self) -> int:
        """Clear all indexed data. Returns count deleted."""
        count = self._collection.count()

        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        return count

    # =========================================================================
    # Internal
    # =========================================================================

    def _format_text(self, dataset: DatasetMetadata) -> str:
        """Format dataset for embedding."""
        parts = []

        if dataset.title:
            parts.append(dataset.title)

        if dataset.abstract:
            parts.append(dataset.abstract)

        return "\n\n".join(parts)

    def _create_metadata(self, dataset: DatasetMetadata) -> dict:
        """Create metadata for ChromaDB."""
        return {
            "title": dataset.title or "",
            "abstract": (dataset.abstract or "")[:1000],
            "keywords": ",".join(dataset.keywords) if dataset.keywords else "",
        }


# =============================================================================
# Console Progress
# =============================================================================

def create_indexing_progress() -> ProgressCallback:
    """Create console progress callback for indexing."""
    last_len = 0

    def callback(dataset_id: str, current: int, total: int) -> None:
        nonlocal last_len

        pct = current / total * 100 if total > 0 else 0
        bar_width = 30
        filled = int(bar_width * current / total)
        bar = "█" * filled + "░" * (bar_width - filled)

        line = f"\r🧠 [{bar}] {pct:5.1f}% ({current}/{total}) {dataset_id[:8]}..."

        padding = " " * max(0, last_len - len(line))
        print(line + padding, end="", flush=True)
        last_len = len(line)

        if current == total:
            print()

    return callback