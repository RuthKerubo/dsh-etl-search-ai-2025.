"""
Resource factory.

Creates appropriate Resource instances based on URL/path patterns.
Implements the Factory pattern for resource creation.
"""

from datetime import timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .base import Resource
from .cached import CachedResource
from .http import (
    CEHCatalogueResource,
    CEHSupportingDocsResource,
    HttpResource,
)
from .local import LocalFileResource, ZipEntryResource


class ResourceFactory:
    """
    Factory for creating Resource instances.

    Automatically determines the appropriate resource type based on
    the URL scheme or path pattern.

    Supports:
    - http://, https:// → HttpResource
    - file:// → LocalFileResource
    - zip:// → ZipEntryResource
    - Regular paths → LocalFileResource

    Example:
        factory = ResourceFactory(cache_dir="./cache")

        # Creates HttpResource
        resource = factory.create("https://example.com/data.json")

        # Creates LocalFileResource
        resource = factory.create("./data/metadata.json")

        # Creates ZipEntryResource
        resource = factory.create("zip://./archive.zip#readme.txt")
    """

    def __init__(
        self,
        cache_dir: Optional[str | Path] = None,
        cache_ttl: Optional[timedelta] = None,
        enable_caching: bool = True,
        default_timeout: float = 30.0,
    ):
        """
        Initialize factory.

        Args:
            cache_dir: Directory for caching (None disables caching)
            cache_ttl: Time-to-live for cached content
            enable_caching: Whether to wrap resources with caching
            default_timeout: Default timeout for HTTP requests
        """
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._cache_ttl = cache_ttl
        self._enable_caching = enable_caching and cache_dir is not None
        self._default_timeout = default_timeout

    def create(
        self,
        url_or_path: str,
        cache: Optional[bool] = None,
        **kwargs,
    ) -> Resource:
        """
        Create a Resource from a URL or path.

        Args:
            url_or_path: URL or file path
            cache: Override caching setting for this resource
            **kwargs: Additional arguments passed to resource constructor

        Returns:
            Appropriate Resource instance
        """
        # Parse the URL/path
        parsed = urlparse(url_or_path)

        # Determine resource type and create
        if parsed.scheme in ("http", "https"):
            resource = self._create_http(url_or_path, **kwargs)
        elif parsed.scheme == "file":
            resource = LocalFileResource(parsed.path)
        elif parsed.scheme == "zip":
            resource = self._create_zip(parsed, **kwargs)
        elif parsed.scheme == "":
            # No scheme - treat as local path
            resource = LocalFileResource(url_or_path)
        else:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        # Wrap with caching if enabled
        should_cache = cache if cache is not None else self._enable_caching
        if should_cache and self._cache_dir:
            resource = CachedResource(
                resource,
                cache_dir=self._cache_dir,
                ttl=self._cache_ttl,
            )

        return resource

    def _create_http(self, url: str, **kwargs) -> HttpResource:
        """Create HTTP resource, using CEH-specific class if appropriate."""
        # Check if this is a CEH catalogue URL
        if "catalogue.ceh.ac.uk" in url:
            return self._create_ceh_resource(url, **kwargs)

        # Check if this is a CEH supporting docs URL
        if "data-package.ceh.ac.uk/sd" in url:
            return self._create_ceh_supporting_docs(url, **kwargs)

        # Generic HTTP resource
        return HttpResource(
            url,
            timeout=kwargs.get("timeout", self._default_timeout),
            **{k: v for k, v in kwargs.items() if k != "timeout"},
        )

    def _create_ceh_resource(self, url: str, **kwargs) -> Resource:
        """Create CEH catalogue resource from URL."""
        # Extract dataset ID and format from URL
        parsed = urlparse(url)

        # Try to extract dataset ID from path
        path_parts = parsed.path.strip("/").split("/")
        dataset_id = None

        for part in path_parts:
            # UUIDs are 36 chars with specific format
            if len(part) >= 36 and "-" in part:
                # Remove any extension
                dataset_id = part.split(".")[0]
                break

        if not dataset_id:
            # Fall back to generic HTTP resource
            return HttpResource(url, **kwargs)

        # Determine format from query string
        format_type = "json"  # Default
        if "format=" in url:
            if "format=gemini" in url:
                format_type = "gemini"
            elif "format=schema.org" in url:
                format_type = "schema.org"
            elif "format=ttl" in url:
                format_type = "ttl"
            elif "format=json" in url:
                format_type = "json"

        return CEHCatalogueResource(
            dataset_id=dataset_id,
            format=format_type,
            timeout=kwargs.get("timeout", self._default_timeout),
            auth=kwargs.get("auth"),
        )

    def _create_ceh_supporting_docs(self, url: str, **kwargs) -> Resource:
        """Create CEH supporting docs resource from URL."""
        parsed = urlparse(url)

        # Extract dataset ID from path like /sd/{uuid}.zip
        path_parts = parsed.path.strip("/").split("/")
        for part in path_parts:
            if part.endswith(".zip"):
                dataset_id = part[:-4]  # Remove .zip
                return CEHSupportingDocsResource(
                    dataset_id=dataset_id,
                    timeout=kwargs.get("timeout", 60.0),
                    auth=kwargs.get("auth"),
                )

        # Fall back to generic HTTP
        return HttpResource(url, **kwargs)

    def _create_zip(self, parsed, **kwargs) -> ZipEntryResource:
        """Create ZIP entry resource from parsed URL."""
        # Format: zip://path/to/archive.zip#entry_name
        zip_path = parsed.path
        entry_name = parsed.fragment

        if not entry_name:
            raise ValueError("ZIP entry URL must include entry name after #")

        return ZipEntryResource(zip_path, entry_name)

    # -------------------------------------------------------------------------
    # Convenience Factory Methods
    # -------------------------------------------------------------------------

    def http(self, url: str, **kwargs) -> Resource:
        """Create HTTP resource."""
        return self.create(url, **kwargs)

    def file(self, path: str | Path, **kwargs) -> Resource:
        """Create local file resource."""
        resource = LocalFileResource(path)

        should_cache = kwargs.get("cache", self._enable_caching)
        if should_cache and self._cache_dir:
            resource = CachedResource(
                resource,
                cache_dir=self._cache_dir,
                ttl=self._cache_ttl,
            )

        return resource

    def zip_entry(
        self,
        zip_path: str | Path,
        entry_name: str,
        **kwargs,
    ) -> Resource:
        """Create ZIP entry resource."""
        resource = ZipEntryResource(zip_path, entry_name)

        should_cache = kwargs.get("cache", self._enable_caching)
        if should_cache and self._cache_dir:
            resource = CachedResource(
                resource,
                cache_dir=self._cache_dir,
                ttl=self._cache_ttl,
            )

        return resource

    def ceh_metadata(
        self,
        dataset_id: str,
        format: str = "json",
        **kwargs,
    ) -> Resource:
        """
        Create CEH catalogue metadata resource.

        Args:
            dataset_id: Dataset UUID
            format: Output format (json, gemini, schema.org, ttl)
            **kwargs: Additional arguments

        Returns:
            CEHCatalogueResource (possibly cached)
        """
        resource = CEHCatalogueResource(
            dataset_id=dataset_id,
            format=format,
            timeout=kwargs.get("timeout", self._default_timeout),
            auth=kwargs.get("auth"),
        )

        should_cache = kwargs.get("cache", self._enable_caching)
        if should_cache and self._cache_dir:
            resource = CachedResource(
                resource,
                cache_dir=self._cache_dir,
                ttl=self._cache_ttl,
            )

        return resource

    def ceh_supporting_docs(
        self,
        dataset_id: str,
        **kwargs,
    ) -> Resource:
        """
        Create CEH supporting documents resource.

        Args:
            dataset_id: Dataset UUID
            **kwargs: Additional arguments

        Returns:
            CEHSupportingDocsResource (possibly cached)
        """
        resource = CEHSupportingDocsResource(
            dataset_id=dataset_id,
            timeout=kwargs.get("timeout", 60.0),
            auth=kwargs.get("auth"),
        )

        should_cache = kwargs.get("cache", self._enable_caching)
        if should_cache and self._cache_dir:
            resource = CachedResource(
                resource,
                cache_dir=self._cache_dir,
                ttl=self._cache_ttl,
            )

        return resource


# Default factory instance
_default_factory: Optional[ResourceFactory] = None


def get_default_factory() -> ResourceFactory:
    """Get or create the default factory instance."""
    global _default_factory
    if _default_factory is None:
        _default_factory = ResourceFactory()
    return _default_factory


def configure_default_factory(
    cache_dir: Optional[str | Path] = None,
    cache_ttl: Optional[timedelta] = None,
    enable_caching: bool = True,
) -> ResourceFactory:
    """
    Configure and return the default factory.

    Args:
        cache_dir: Directory for caching
        cache_ttl: Time-to-live for cache
        enable_caching: Whether to enable caching

    Returns:
        Configured ResourceFactory
    """
    global _default_factory
    _default_factory = ResourceFactory(
        cache_dir=cache_dir,
        cache_ttl=cache_ttl,
        enable_caching=enable_caching,
    )
    return _default_factory