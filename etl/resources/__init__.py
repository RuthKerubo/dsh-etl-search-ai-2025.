"""
Resource abstraction layer for the ETL pipeline.

This module provides a uniform interface for fetching data from
various sources (HTTP, local files, ZIP archives) with built-in
caching support.

Design Patterns:
    - Template Method: Base Resource class defines fetch algorithm
    - Decorator: CachedResource wraps any Resource to add caching
    - Factory: ResourceFactory creates appropriate Resource types
    - Strategy: Different Resource implementations for different sources

Example:
    from etl.resources import ResourceFactory
    from datetime import timedelta

    factory = ResourceFactory(
        cache_dir="./data/cache",
        cache_ttl=timedelta(hours=24),
    )

    # Fetch CEH metadata
    resource = factory.ceh_metadata("f710bed1-...", format="json")
    result = await resource.fetch()

    if result.success:
        data = json.loads(result.text)
"""

# Base classes and types
from .base import (
    FetchResult,
    Resource,
    ResourceMetadata,
    ResourceType,
)

# HTTP resources
from .http import (
    CEHCatalogueResource,
    CEHSupportingDocsResource,
    HttpResource,
)

# Local resources
from .local import (
    LocalFileResource,
    ZipEntryResource,
    extract_zip_to_directory,
)

# Caching
from .cached import (
    CachedResource,
    cache_stats,
    clear_cache,
)

# Factory
from .factory import (
    ResourceFactory,
    configure_default_factory,
    get_default_factory,
)


__all__ = [
    # Base
    "FetchResult",
    "Resource",
    "ResourceMetadata",
    "ResourceType",
    # HTTP
    "CEHCatalogueResource",
    "CEHSupportingDocsResource",
    "HttpResource",
    # Local
    "LocalFileResource",
    "ZipEntryResource",
    "extract_zip_to_directory",
    # Caching
    "CachedResource",
    "cache_stats",
    "clear_cache",
    # Factory
    "ResourceFactory",
    "configure_default_factory",
    "get_default_factory",
]