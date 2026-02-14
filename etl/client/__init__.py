"""
CEH Catalogue Client.

High-level client for fetching datasets from the CEH Environmental Information
Data Centre. Orchestrates the resource layer with rate limiting, concurrency
control, and progress reporting.

Design decisions:
- Fetches JSON (primary) + XML (raw storage) per dataset
- Async with controlled concurrency (default: 3)
- Rate limiting via semaphore + delay
- Continues on partial failures, reports at end

Usage:
    client = CEHCatalogueClient(
        cache_dir="./data/cache",
        concurrency=3,
        request_delay=0.3,
    )

    results = await client.fetch_all(dataset_ids, progress_callback=callback)
    print(f"Success: {len(results.successful)}, Failed: {len(results.failed)}")
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from etl.resources import (
    ResourceFactory,
    CEHCatalogueResource,
    CEHSupportingDocsResource,
    CachedResource,
)
from etl.resources.base import FetchResult


class FetchFormat(str, Enum):
    """Available metadata formats."""
    JSON = "json"
    XML = "gemini"
    JSONLD = "schema.org"
    TURTLE = "ttl"


@dataclass
class DatasetFetchResult:
    """Result of fetching a single dataset."""
    dataset_id: str
    success: bool

    # Content by format
    json_content: Optional[str] = None
    xml_content: Optional[str] = None

    # Metadata
    fetch_duration_ms: float = 0
    from_cache: bool = False

    # Error info (if failed)
    error: Optional[str] = None
    failed_format: Optional[str] = None


@dataclass
class BatchFetchResult:
    """Result of fetching multiple datasets."""
    successful: list[DatasetFetchResult] = field(default_factory=list)
    failed: list[DatasetFetchResult] = field(default_factory=list)

    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @property
    def total(self) -> int:
        return len(self.successful) + len(self.failed)

    @property
    def success_rate(self) -> float:
        return len(self.successful) / self.total if self.total > 0 else 0.0

    @property
    def duration(self) -> timedelta:
        end = self.completed_at or datetime.utcnow()
        return end - self.started_at

    @property
    def cache_hit_rate(self) -> float:
        cached = sum(1 for r in self.successful if r.from_cache)
        return cached / len(self.successful) if self.successful else 0.0

    def summary(self) -> str:
        return (
            f"Fetched {self.total} datasets: "
            f"{len(self.successful)} succeeded ({self.success_rate:.1%}), "
            f"{len(self.failed)} failed. "
            f"Cache hit rate: {self.cache_hit_rate:.1%}. "
            f"Duration: {self.duration.total_seconds():.1f}s"
        )


@dataclass
class ProgressUpdate:
    """Progress update for fetch operations."""
    dataset_id: str
    current: int
    total: int
    status: str  # "fetching", "completed", "failed"
    from_cache: bool = False
    error: Optional[str] = None

    @property
    def progress_pct(self) -> float:
        return (self.current / self.total * 100) if self.total > 0 else 0


# Type alias for progress callback
ProgressCallback = Callable[[ProgressUpdate], None]


class CEHCatalogueClient:
    """
    Client for fetching datasets from CEH Catalogue.

    Features:
    - Concurrent fetching with rate limiting
    - Automatic caching via ResourceFactory
    - Progress reporting
    - Graceful partial failure handling

    Example:
        client = CEHCatalogueClient(cache_dir="./cache")

        # Fetch with progress
        def on_progress(update):
            print(f"[{update.current}/{update.total}] {update.dataset_id}: {update.status}")

        results = await client.fetch_all(dataset_ids, progress_callback=on_progress)

        for result in results.successful:
            print(f"Got {result.dataset_id}: {len(result.json_content)} bytes")
    """

    # CEH Catalogue base URLs
    BASE_URL = "https://catalogue.ceh.ac.uk"
    SUPPORTING_DOCS_URL = "https://data-package.ceh.ac.uk/sd"

    def __init__(
        self,
        cache_dir: Optional[str | Path] = None,
        cache_ttl: Optional[timedelta] = None,
        concurrency: int = 3,
        request_delay: float = 0.3,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize the client.

        Args:
            cache_dir: Directory for caching responses (None disables caching)
            cache_ttl: Cache time-to-live (None = cache forever)
            concurrency: Maximum concurrent requests
            request_delay: Delay between requests (rate limiting)
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts per request
        """
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._cache_ttl = cache_ttl
        self._concurrency = concurrency
        self._request_delay = request_delay
        self._timeout = timeout
        self._max_retries = max_retries

        # Create resource factory
        self._factory = ResourceFactory(
            cache_dir=cache_dir,
            cache_ttl=cache_ttl,
            enable_caching=cache_dir is not None,
            default_timeout=timeout,
        )

        # Semaphore for concurrency control
        self._semaphore: Optional[asyncio.Semaphore] = None

    # =========================================================================
    # Public API
    # =========================================================================

    async def fetch_dataset(
        self,
        dataset_id: str,
        formats: list[FetchFormat] | None = None,
    ) -> DatasetFetchResult:
        """
        Fetch a single dataset's metadata.

        Args:
            dataset_id: Dataset UUID
            formats: Formats to fetch (default: JSON + XML)

        Returns:
            DatasetFetchResult with content or error
        """
        formats = formats or [FetchFormat.JSON, FetchFormat.XML]
        start_time = datetime.utcnow()

        result = DatasetFetchResult(dataset_id=dataset_id, success=True)

        try:
            for fmt in formats:
                content, from_cache = await self._fetch_format(dataset_id, fmt)

                if fmt == FetchFormat.JSON:
                    result.json_content = content
                elif fmt == FetchFormat.XML:
                    result.xml_content = content

                result.from_cache = result.from_cache or from_cache

            result.fetch_duration_ms = (
                datetime.utcnow() - start_time
            ).total_seconds() * 1000

        except Exception as e:
            result.success = False
            result.error = str(e)
            result.failed_format = fmt.value if 'fmt' in locals() else None

        return result

    async def fetch_all(
        self,
        dataset_ids: list[str],
        formats: list[FetchFormat] | None = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> BatchFetchResult:
        """
        Fetch multiple datasets concurrently.

        Args:
            dataset_ids: List of dataset UUIDs
            formats: Formats to fetch (default: JSON + XML)
            progress_callback: Optional callback for progress updates

        Returns:
            BatchFetchResult with successful and failed results
        """
        formats = formats or [FetchFormat.JSON, FetchFormat.XML]
        batch_result = BatchFetchResult()
        total = len(dataset_ids)

        # Initialize semaphore for this batch
        self._semaphore = asyncio.Semaphore(self._concurrency)

        async def fetch_with_progress(index: int, dataset_id: str):
            """Fetch single dataset with progress reporting."""
            # Notify start
            if progress_callback:
                progress_callback(ProgressUpdate(
                    dataset_id=dataset_id,
                    current=index,
                    total=total,
                    status="fetching",
                ))

            # Acquire semaphore (rate limiting)
            async with self._semaphore:
                result = await self.fetch_dataset(dataset_id, formats)

                # Rate limit delay
                await asyncio.sleep(self._request_delay)

            # Notify completion
            if progress_callback:
                progress_callback(ProgressUpdate(
                    dataset_id=dataset_id,
                    current=index + 1,
                    total=total,
                    status="completed" if result.success else "failed",
                    from_cache=result.from_cache,
                    error=result.error,
                ))

            return result

        # Create tasks for all datasets
        tasks = [
            fetch_with_progress(i, dataset_id)
            for i, dataset_id in enumerate(dataset_ids)
        ]

        # Execute all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Categorize results
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # Task raised exception
                batch_result.failed.append(DatasetFetchResult(
                    dataset_id=dataset_ids[i],
                    success=False,
                    error=str(result),
                ))
            elif result.success:
                batch_result.successful.append(result)
            else:
                batch_result.failed.append(result)

        batch_result.completed_at = datetime.utcnow()
        return batch_result

    async def fetch_supporting_docs(
        self,
        dataset_id: str,
    ) -> tuple[bytes | None, str | None]:
        """
        Fetch supporting documents ZIP for a dataset.

        Args:
            dataset_id: Dataset UUID

        Returns:
            Tuple of (zip_bytes, error_message)
        """
        try:
            resource = self._factory.ceh_supporting_docs(dataset_id)
            result = await resource.fetch()

            if result.success:
                return result.content, None
            return None, result.error

        except Exception as e:
            return None, str(e)

    def stream_datasets(
        self,
        dataset_ids: list[str],
        formats: list[FetchFormat] | None = None,
    ) -> AsyncIterator[DatasetFetchResult]:
        """
        Stream dataset fetch results as they complete.

        Useful for processing results as they arrive rather than
        waiting for all to complete.

        Args:
            dataset_ids: List of dataset UUIDs
            formats: Formats to fetch

        Yields:
            DatasetFetchResult as each completes
        """
        return self._stream_fetch(dataset_ids, formats)

    async def _stream_fetch(
        self,
        dataset_ids: list[str],
        formats: list[FetchFormat] | None = None,
    ) -> AsyncIterator[DatasetFetchResult]:
        """Internal streaming implementation."""
        formats = formats or [FetchFormat.JSON, FetchFormat.XML]
        self._semaphore = asyncio.Semaphore(self._concurrency)

        async def fetch_one(dataset_id: str) -> DatasetFetchResult:
            async with self._semaphore:
                result = await self.fetch_dataset(dataset_id, formats)
                await asyncio.sleep(self._request_delay)
                return result

        # Create tasks
        pending = {
            asyncio.create_task(fetch_one(did)): did
            for did in dataset_ids
        }

        # Yield as they complete
        while pending:
            done, _ = await asyncio.wait(
                pending.keys(),
                return_when=asyncio.FIRST_COMPLETED,
            )

            for task in done:
                dataset_id = pending.pop(task)
                try:
                    yield task.result()
                except Exception as e:
                    yield DatasetFetchResult(
                        dataset_id=dataset_id,
                        success=False,
                        error=str(e),
                    )

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _fetch_format(
        self,
        dataset_id: str,
        fmt: FetchFormat,
    ) -> tuple[str, bool]:
        """
        Fetch a single format for a dataset.

        Returns:
            Tuple of (content, from_cache)
        """
        resource = self._factory.ceh_metadata(
            dataset_id=dataset_id,
            format=fmt.value,
        )

        result = await resource.fetch()

        if not result.success:
            raise FetchError(
                f"Failed to fetch {fmt.value} for {dataset_id}: {result.error}"
            )

        return result.text, result.from_cache

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def check_dataset_exists(self, dataset_id: str) -> bool:
        """Check if a dataset exists in the catalogue."""
        resource = CEHCatalogueResource(dataset_id=dataset_id, format="json")
        return await resource.exists()

    async def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        if not self._cache_dir:
            return {"enabled": False}

        from etl.resources.cached import cache_stats
        stats = await cache_stats(self._cache_dir)
        stats["enabled"] = True
        return stats

    async def clear_cache(self) -> int:
        """Clear the cache. Returns number of entries cleared."""
        if not self._cache_dir:
            return 0

        from etl.resources.cached import clear_cache
        return await clear_cache(self._cache_dir)


class FetchError(Exception):
    """Error during fetch operation."""
    pass


# =============================================================================
# Console Progress Display
# =============================================================================

def create_console_progress() -> ProgressCallback:
    """
    Create a progress callback that prints to console.

    Usage:
        results = await client.fetch_all(ids, progress_callback=create_console_progress())
    """
    last_line_len = 0

    def callback(update: ProgressUpdate) -> None:
        nonlocal last_line_len

        status_icons = {
            "fetching": "📥",
            "completed": "✅" if not update.from_cache else "💾",
            "failed": "❌",
        }
        icon = status_icons.get(update.status, "⏳")

        bar_width = 30
        filled = int(bar_width * update.current / update.total)
        bar = "█" * filled + "░" * (bar_width - filled)

        line = (
            f"\r{icon} [{bar}] {update.progress_pct:5.1f}% "
            f"({update.current}/{update.total}) "
            f"{update.dataset_id[:8]}..."
        )

        if update.error:
            line += f" Error: {update.error[:30]}"

        padding = " " * max(0, last_line_len - len(line))
        print(line + padding, end="", flush=True)
        last_line_len = len(line)

        if update.current == update.total:
            print()  # Newline at end

    return callback


# =============================================================================
# Convenience Functions
# =============================================================================

async def fetch_datasets(
    dataset_ids: list[str],
    cache_dir: str = "./data/cache",
    show_progress: bool = True,
) -> BatchFetchResult:
    """
    Convenience function to fetch datasets with sensible defaults.

    Args:
        dataset_ids: List of dataset UUIDs
        cache_dir: Cache directory
        show_progress: Whether to show console progress

    Returns:
        BatchFetchResult
    """
    client = CEHCatalogueClient(
        cache_dir=cache_dir,
        cache_ttl=timedelta(hours=24),
    )

    callback = create_console_progress() if show_progress else None
    return await client.fetch_all(dataset_ids, progress_callback=callback)