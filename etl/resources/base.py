"""
Abstract Resource base class.

This module defines the Resource abstraction that allows the ETL pipeline
to work with any data source without knowing implementation details.

Design Patterns:
    - Template Method: Base class defines algorithm, subclasses implement steps
    - Liskov Substitution: All subclasses are interchangeable

SOLID Principles:
    - Single Responsibility: One class = one resource type
    - Open/Closed: Add new types without modifying existing code
    - Dependency Inversion: Clients depend on Resource abstraction
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import AsyncIterator, Optional
import hashlib


class ResourceType(str, Enum):
    """Types of resources the system can handle."""
    HTTP = "http"
    LOCAL_FILE = "local_file"
    ZIP_ENTRY = "zip_entry"
    CACHED = "cached"


@dataclass
class ResourceMetadata:
    """
    Metadata about a resource.

    Provides information about the resource without fetching its content.
    Useful for caching decisions and progress reporting.

    Attributes:
        content_type: MIME type of the resource
        size_bytes: Size in bytes (if known)
        last_modified: Last modification timestamp (if known)
        etag: HTTP ETag or content hash (if available)
        encoding: Character encoding (if applicable)
    """
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    last_modified: Optional[datetime] = None
    etag: Optional[str] = None
    encoding: Optional[str] = None
    extra: dict = field(default_factory=dict)

    @property
    def is_json(self) -> bool:
        """Check if content type indicates JSON."""
        if not self.content_type:
            return False
        return "json" in self.content_type.lower()

    @property
    def is_xml(self) -> bool:
        """Check if content type indicates XML."""
        if not self.content_type:
            return False
        ct = self.content_type.lower()
        return "xml" in ct or "gemini" in ct

    @property
    def is_text(self) -> bool:
        """Check if content type indicates text."""
        if not self.content_type:
            return False
        return self.content_type.lower().startswith("text/")


@dataclass
class FetchResult:
    """
    Result of fetching a resource.

    Encapsulates the fetched content along with metadata and status.

    Attributes:
        content: Raw bytes of the resource
        metadata: Resource metadata
        success: Whether the fetch succeeded
        error: Error message if fetch failed
        from_cache: Whether content came from cache
    """
    content: bytes
    metadata: ResourceMetadata
    success: bool = True
    error: Optional[str] = None
    from_cache: bool = False

    @property
    def text(self) -> str:
        """Decode content as text using detected or default encoding."""
        encoding = self.metadata.encoding or "utf-8"
        return self.content.decode(encoding)

    @property
    def content_hash(self) -> str:
        """SHA-256 hash of content for change detection."""
        return hashlib.sha256(self.content).hexdigest()

    @classmethod
    def failure(cls, error: str) -> "FetchResult":
        """Create a failed result."""
        return cls(
            content=b"",
            metadata=ResourceMetadata(),
            success=False,
            error=error,
        )


class Resource(ABC):
    """
    Abstract base class for all resource types.

    This abstraction allows the ETL pipeline to work with any data source
    (HTTP, local files, ZIP archives, etc.) using a uniform interface.

    The fetch() method uses the Template Method pattern:
    1. Validates the resource (common)
    2. Calls _do_fetch() (abstract - implemented by subclasses)
    3. Post-processes the result (common)

    Subclasses must implement:
        - _do_fetch(): Actual fetching logic
        - exists(): Check if resource is available
        - identifier: Unique identifier for the resource
        - resource_type: Type of resource

    Example:
        resource = HttpResource("https://example.com/data.json")
        if await resource.exists():
            result = await resource.fetch()
            data = json.loads(result.text)
    """

    # -------------------------------------------------------------------------
    # Abstract Methods (Subclasses Must Implement)
    # -------------------------------------------------------------------------

    @abstractmethod
    async def _do_fetch(self) -> FetchResult:
        """
        Perform the actual fetch operation.

        This is the Template Method hook - subclasses implement
        their specific fetching logic here.

        Returns:
            FetchResult with content and metadata
        """
        pass

    @abstractmethod
    async def exists(self) -> bool:
        """
        Check if the resource exists and is accessible.

        Returns:
            True if resource can be fetched, False otherwise
        """
        pass

    @property
    @abstractmethod
    def identifier(self) -> str:
        """
        Unique identifier for this resource.

        Used for caching, logging, and deduplication.
        For HTTP resources, this is typically the URL.
        For files, this is the absolute path.
        """
        pass

    @property
    @abstractmethod
    def resource_type(self) -> ResourceType:
        """Type of this resource."""
        pass

    # -------------------------------------------------------------------------
    # Template Method
    # -------------------------------------------------------------------------

    async def fetch(self) -> FetchResult:
        """
        Fetch the resource content.

        This is the Template Method that defines the fetch algorithm:
        1. Pre-fetch validation
        2. Actual fetch (delegated to subclass)
        3. Post-fetch processing

        Returns:
            FetchResult with content, metadata, and status
        """
        # Pre-fetch validation
        if not await self._validate():
            return FetchResult.failure(f"Validation failed for {self.identifier}")

        try:
            # Delegate to subclass implementation
            result = await self._do_fetch()

            # Post-fetch processing
            if result.success:
                result = await self._post_process(result)

            return result

        except Exception as e:
            return FetchResult.failure(f"Fetch failed: {str(e)}")

    # -------------------------------------------------------------------------
    # Hook Methods (Can Be Overridden)
    # -------------------------------------------------------------------------

    async def _validate(self) -> bool:
        """
        Validate before fetching.

        Override to add custom validation logic.
        Default implementation always returns True.
        """
        return True

    async def _post_process(self, result: FetchResult) -> FetchResult:
        """
        Post-process the fetch result.

        Override to add custom processing (e.g., decompression).
        Default implementation returns result unchanged.
        """
        return result

    # -------------------------------------------------------------------------
    # Optional Methods
    # -------------------------------------------------------------------------

    async def get_metadata(self) -> ResourceMetadata:
        """
        Get metadata without fetching full content.

        Default implementation fetches content and extracts metadata.
        Subclasses can override for more efficient metadata-only requests.
        """
        result = await self.fetch()
        return result.metadata

    async def stream(self, chunk_size: int = 8192) -> AsyncIterator[bytes]:
        """
        Stream resource content in chunks.

        Default implementation fetches all content then yields chunks.
        Subclasses can override for true streaming.

        Args:
            chunk_size: Size of each chunk in bytes

        Yields:
            Chunks of content
        """
        result = await self.fetch()
        content = result.content

        for i in range(0, len(content), chunk_size):
            yield content[i:i + chunk_size]

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.identifier})>"

    def __hash__(self) -> int:
        return hash(self.identifier)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Resource):
            return False
        return self.identifier == other.identifier