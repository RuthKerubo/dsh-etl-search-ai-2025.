"""
Cached resource decorator.

Implements the Decorator pattern to add caching to any Resource.
The cache is transparent - clients don't need to know if content
comes from cache or the original source.
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiofiles
import aiofiles.os

from .base import (
    FetchResult,
    Resource,
    ResourceMetadata,
    ResourceType,
)


class CachedResource(Resource):
    """
    Decorator that adds caching to any Resource.

    Wraps another Resource and caches its content to disk.
    On subsequent fetches, returns cached content if still valid.

    Cache invalidation strategies:
    - TTL (time-to-live): Cache expires after specified duration
    - ETag: Revalidate with server if ETag changes
    - Force refresh: Bypass cache on demand

    The cache is organized by resource identifier hash:
        cache_dir/
            ab/
                abc123def456.content   # Raw content
                abc123def456.meta      # Metadata JSON

    Example:
        # Wrap an HTTP resource with caching
        http_resource = HttpResource("https://example.com/data.json")
        cached = CachedResource(
            http_resource,
            cache_dir="./cache",
            ttl=timedelta(hours=24),
        )

        # First fetch - hits network, caches result
        result = await cached.fetch()

        # Second fetch - returns from cache
        result = await cached.fetch()
        assert result.from_cache == True

    Attributes:
        wrapped: The underlying resource being cached
        cache_dir: Directory for cache storage
        ttl: Time-to-live for cache entries
    """

    def __init__(
        self,
        wrapped: Resource,
        cache_dir: str | Path,
        ttl: Optional[timedelta] = None,
        use_etag: bool = True,
    ):
        """
        Initialize cached resource.

        Args:
            wrapped: Resource to cache
            cache_dir: Directory for cache storage
            ttl: Time-to-live (None = cache forever)
            use_etag: Whether to use ETag for revalidation
        """
        self._wrapped = wrapped
        self._cache_dir = Path(cache_dir)
        self._ttl = ttl
        self._use_etag = use_etag

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def identifier(self) -> str:
        """Use wrapped resource's identifier."""
        return self._wrapped.identifier

    @property
    def resource_type(self) -> ResourceType:
        return ResourceType.CACHED

    @property
    def wrapped(self) -> Resource:
        """The underlying resource."""
        return self._wrapped

    @property
    def wrapped_type(self) -> ResourceType:
        """Type of the wrapped resource."""
        return self._wrapped.resource_type

    async def exists(self) -> bool:
        """Check if resource exists (in cache or at source)."""
        if await self._cache_exists():
            return True
        return await self._wrapped.exists()

    async def _do_fetch(self) -> FetchResult:
        """
        Fetch with caching.

        1. Check if valid cache exists
        2. If yes, return cached content
        3. If no, fetch from source and cache
        """
        # Check cache first
        cached = await self._read_cache()
        if cached is not None:
            if await self._is_cache_valid(cached):
                cached.from_cache = True
                return cached

        # Fetch from source
        result = await self._wrapped.fetch()

        if result.success:
            # Store in cache
            await self._write_cache(result)

        return result

    async def fetch_fresh(self) -> FetchResult:
        """
        Fetch bypassing cache.

        Forces a fresh fetch from the source and updates cache.
        """
        result = await self._wrapped.fetch()

        if result.success:
            await self._write_cache(result)

        return result

    async def invalidate(self) -> bool:
        """
        Invalidate (delete) the cache for this resource.

        Returns:
            True if cache was deleted, False if no cache existed
        """
        content_path, meta_path = self._cache_paths()

        deleted = False

        if await aiofiles.os.path.exists(content_path):
            await aiofiles.os.remove(content_path)
            deleted = True

        if await aiofiles.os.path.exists(meta_path):
            await aiofiles.os.remove(meta_path)
            deleted = True

        return deleted

    # -------------------------------------------------------------------------
    # Cache Management
    # -------------------------------------------------------------------------

    def _cache_key(self) -> str:
        """Generate cache key from identifier."""
        return hashlib.sha256(self.identifier.encode()).hexdigest()

    def _cache_paths(self) -> tuple[Path, Path]:
        """Get paths for cache content and metadata files."""
        key = self._cache_key()

        # Use first 2 chars as subdirectory for better filesystem performance
        subdir = self._cache_dir / key[:2]

        content_path = subdir / f"{key}.content"
        meta_path = subdir / f"{key}.meta"

        return content_path, meta_path

    async def _cache_exists(self) -> bool:
        """Check if cache files exist."""
        content_path, meta_path = self._cache_paths()
        return (
            await aiofiles.os.path.exists(content_path) and
            await aiofiles.os.path.exists(meta_path)
        )

    async def _read_cache(self) -> Optional[FetchResult]:
        """Read cached content and metadata."""
        content_path, meta_path = self._cache_paths()

        try:
            # Read metadata
            async with aiofiles.open(meta_path, "r") as f:
                meta_json = await f.read()
            meta_dict = json.loads(meta_json)

            # Read content
            async with aiofiles.open(content_path, "rb") as f:
                content = await f.read()

            # Reconstruct metadata
            metadata = ResourceMetadata(
                content_type=meta_dict.get("content_type"),
                size_bytes=meta_dict.get("size_bytes"),
                last_modified=datetime.fromisoformat(meta_dict["last_modified"])
                    if meta_dict.get("last_modified") else None,
                etag=meta_dict.get("etag"),
                encoding=meta_dict.get("encoding"),
                extra=meta_dict.get("extra", {}),
            )

            # Add cache metadata
            metadata.extra["cached_at"] = meta_dict.get("cached_at")
            metadata.extra["cache_key"] = self._cache_key()

            return FetchResult(
                content=content,
                metadata=metadata,
                success=True,
                from_cache=True,
            )

        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None

    async def _write_cache(self, result: FetchResult) -> None:
        """Write content and metadata to cache."""
        content_path, meta_path = self._cache_paths()

        # Ensure subdirectory exists
        content_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        async with aiofiles.open(content_path, "wb") as f:
            await f.write(result.content)

        # Build metadata dict
        meta_dict = {
            "content_type": result.metadata.content_type,
            "size_bytes": result.metadata.size_bytes,
            "last_modified": result.metadata.last_modified.isoformat()
                if result.metadata.last_modified else None,
            "etag": result.metadata.etag,
            "encoding": result.metadata.encoding,
            "extra": result.metadata.extra,
            "cached_at": datetime.utcnow().isoformat(),
            "identifier": self.identifier,
        }

        # Write metadata
        async with aiofiles.open(meta_path, "w") as f:
            await f.write(json.dumps(meta_dict, indent=2))

    async def _is_cache_valid(self, cached: FetchResult) -> bool:
        """Check if cached content is still valid."""
        # Check TTL
        if self._ttl is not None:
            cached_at_str = cached.metadata.extra.get("cached_at")
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                if datetime.utcnow() - cached_at > self._ttl:
                    return False

        # ETag revalidation could be added here
        # For now, if within TTL, consider valid

        return True

    # -------------------------------------------------------------------------
    # Cache Statistics
    # -------------------------------------------------------------------------

    async def cache_info(self) -> dict:
        """
        Get information about this resource's cache.

        Returns:
            Dict with cache status and metadata
        """
        content_path, meta_path = self._cache_paths()

        if not await aiofiles.os.path.exists(meta_path):
            return {"cached": False}

        try:
            async with aiofiles.open(meta_path, "r") as f:
                meta_dict = json.loads(await f.read())

            cached_at = datetime.fromisoformat(meta_dict["cached_at"])

            is_valid = True
            if self._ttl is not None:
                is_valid = datetime.utcnow() - cached_at <= self._ttl

            return {
                "cached": True,
                "cached_at": cached_at,
                "valid": is_valid,
                "size_bytes": meta_dict.get("size_bytes"),
                "content_type": meta_dict.get("content_type"),
                "cache_key": self._cache_key(),
            }

        except Exception:
            return {"cached": False, "error": "Failed to read cache metadata"}


async def clear_cache(cache_dir: str | Path) -> int:
    """
    Clear all cached content.

    Args:
        cache_dir: Cache directory to clear

    Returns:
        Number of cache entries deleted
    """
    import shutil

    cache_dir = Path(cache_dir)

    if not cache_dir.exists():
        return 0

    count = 0
    for subdir in cache_dir.iterdir():
        if subdir.is_dir():
            for file in subdir.iterdir():
                file.unlink()
                count += 1
            subdir.rmdir()

    return count // 2  # Two files per entry (content + meta)


async def cache_stats(cache_dir: str | Path) -> dict:
    """
    Get statistics about the cache.

    Args:
        cache_dir: Cache directory

    Returns:
        Dict with cache statistics
    """
    cache_dir = Path(cache_dir)

    if not cache_dir.exists():
        return {"entries": 0, "total_bytes": 0}

    entries = 0
    total_bytes = 0

    for subdir in cache_dir.iterdir():
        if subdir.is_dir():
            for file in subdir.iterdir():
                if file.suffix == ".content":
                    entries += 1
                    stat = await aiofiles.os.stat(file)
                    total_bytes += stat.st_size

    return {
        "entries": entries,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
    }