"""
HTTP Resource implementation.

Fetches content from HTTP/HTTPS URLs using aiohttp for async operations.
Includes retry logic, timeout handling, and proper error management.
"""

import asyncio
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import aiohttp

from .base import (
    FetchResult,
    Resource,
    ResourceMetadata,
    ResourceType,
)


class HttpResource(Resource):
    """
    Resource fetched via HTTP/HTTPS.

    Uses aiohttp for async HTTP requests with:
    - Configurable timeouts
    - Retry logic for transient failures
    - Proper header handling
    - Authentication support

    Attributes:
        url: The URL to fetch
        headers: Optional headers to include in request
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts for transient failures
        auth: Optional (username, password) tuple

    Example:
        resource = HttpResource(
            "https://catalogue.ceh.ac.uk/id/abc123?format=json",
            headers={"Accept": "application/json"},
        )
        result = await resource.fetch()
        data = json.loads(result.text)
    """

    # Transient HTTP status codes that warrant retry
    RETRY_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        auth: Optional[tuple[str, str]] = None,
    ):
        """
        Initialize HTTP resource.

        Args:
            url: URL to fetch
            headers: Optional HTTP headers
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts
            retry_delay: Base delay between retries (exponential backoff)
            auth: Optional (username, password) for basic auth
        """
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._auth = auth

        # Validate URL
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Invalid URL scheme: {parsed.scheme}")

    @property
    def identifier(self) -> str:
        """URL is the unique identifier."""
        return self._url

    @property
    def resource_type(self) -> ResourceType:
        return ResourceType.HTTP

    @property
    def url(self) -> str:
        """The URL being fetched."""
        return self._url

    async def exists(self) -> bool:
        """
        Check if resource exists using HEAD request.

        Returns:
            True if resource returns 2xx status, False otherwise
        """
        try:
            async with aiohttp.ClientSession() as session:
                auth = None
                if self._auth:
                    auth = aiohttp.BasicAuth(self._auth[0], self._auth[1])

                async with session.head(
                    self._url,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                    auth=auth,
                    allow_redirects=True,
                ) as response:
                    return response.status < 400
        except Exception:
            return False

    async def _do_fetch(self) -> FetchResult:
        """
        Fetch content from URL with retry logic.

        Implements exponential backoff for transient failures.
        """
        last_error: Optional[str] = None

        for attempt in range(self._max_retries):
            try:
                result = await self._single_fetch()

                if result.success:
                    return result

                # Check if we should retry
                status_code = result.metadata.extra.get("status_code", 0)
                if status_code not in self.RETRY_STATUS_CODES:
                    return result  # Don't retry non-transient errors

                last_error = result.error

            except aiohttp.ClientError as e:
                last_error = str(e)
            except asyncio.TimeoutError:
                last_error = f"Request timed out after {self._timeout}s"
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"

            # Exponential backoff before retry
            if attempt < self._max_retries - 1:
                delay = self._retry_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        return FetchResult.failure(
            f"Failed after {self._max_retries} attempts: {last_error}"
        )

    async def _single_fetch(self) -> FetchResult:
        """Perform a single fetch attempt."""
        async with aiohttp.ClientSession() as session:
            auth = None
            if self._auth:
                auth = aiohttp.BasicAuth(self._auth[0], self._auth[1])

            async with session.get(
                self._url,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                auth=auth,
                allow_redirects=True,
            ) as response:

                # Build metadata from response headers
                metadata = self._build_metadata(response)

                if response.status >= 400:
                    return FetchResult(
                        content=b"",
                        metadata=metadata,
                        success=False,
                        error=f"HTTP {response.status}: {response.reason}",
                    )

                content = await response.read()

                return FetchResult(
                    content=content,
                    metadata=metadata,
                    success=True,
                )

    def _build_metadata(self, response: aiohttp.ClientResponse) -> ResourceMetadata:
        """Extract metadata from HTTP response."""
        # Parse content type
        content_type = response.content_type

        # Parse content length
        size_bytes = response.content_length

        # Parse last modified
        last_modified = None
        if "Last-Modified" in response.headers:
            try:
                from email.utils import parsedate_to_datetime
                last_modified = parsedate_to_datetime(
                    response.headers["Last-Modified"]
                )
            except (ValueError, TypeError):
                pass

        # Get ETag
        etag = response.headers.get("ETag")

        # Get encoding
        encoding = response.charset or "utf-8"

        return ResourceMetadata(
            content_type=content_type,
            size_bytes=size_bytes,
            last_modified=last_modified,
            etag=etag,
            encoding=encoding,
            extra={
                "status_code": response.status,
                "url": str(response.url),  # Final URL after redirects
                "headers": dict(response.headers),
            },
        )

    async def get_metadata(self) -> ResourceMetadata:
        """
        Get metadata using HEAD request (more efficient).

        Falls back to GET if HEAD fails.
        """
        try:
            async with aiohttp.ClientSession() as session:
                auth = None
                if self._auth:
                    auth = aiohttp.BasicAuth(self._auth[0], self._auth[1])

                async with session.head(
                    self._url,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                    auth=auth,
                    allow_redirects=True,
                ) as response:
                    if response.status < 400:
                        return self._build_metadata(response)
        except Exception:
            pass

        # Fall back to full fetch
        result = await self.fetch()
        return result.metadata


class CEHCatalogueResource(HttpResource):
    """
    Specialized HTTP resource for CEH Catalogue API.

    Pre-configures headers and URL patterns for CEH catalogue access.

    Example:
        resource = CEHCatalogueResource(
            dataset_id="f710bed1-e564-47bf-b82c-4c2a2fe2810e",
            format="json",
        )
        result = await resource.fetch()
    """

    BASE_URL = "https://catalogue.ceh.ac.uk"

    # Format to Accept header mapping
    FORMAT_HEADERS = {
        "json": {"Accept": "application/json"},
        "gemini": {"Accept": "application/xml"},
        "schema.org": {"Accept": "application/ld+json"},
        "ttl": {"Accept": "text/turtle"},
    }

    def __init__(
        self,
        dataset_id: str,
        format: str = "json",
        auth: Optional[tuple[str, str]] = None,
        timeout: float = 30.0,
    ):
        """
        Initialize CEH catalogue resource.

        Args:
            dataset_id: Dataset UUID
            format: Output format (json, gemini, schema.org, ttl)
            auth: Optional (username, password) for authenticated datasets
            timeout: Request timeout
        """
        self._dataset_id = dataset_id
        self._format = format

        # Build URL based on format
        url = self._build_url(dataset_id, format)

        # Get appropriate headers
        headers = self.FORMAT_HEADERS.get(format, {})

        super().__init__(
            url=url,
            headers=headers,
            auth=auth,
            timeout=timeout,
        )

    @classmethod
    def _build_url(cls, dataset_id: str, format: str) -> str:
        """Build the appropriate URL for the format."""
        if format == "gemini":
            return f"{cls.BASE_URL}/id/{dataset_id}.xml?format=gemini"
        else:
            return f"{cls.BASE_URL}/id/{dataset_id}?format={format}"

    @property
    def dataset_id(self) -> str:
        """The dataset ID being fetched."""
        return self._dataset_id

    @property
    def format(self) -> str:
        """The format being requested."""
        return self._format

    @classmethod
    def json(cls, dataset_id: str, **kwargs) -> "CEHCatalogueResource":
        """Factory for JSON format."""
        return cls(dataset_id, format="json", **kwargs)

    @classmethod
    def xml(cls, dataset_id: str, **kwargs) -> "CEHCatalogueResource":
        """Factory for ISO 19115 XML format."""
        return cls(dataset_id, format="gemini", **kwargs)

    @classmethod
    def jsonld(cls, dataset_id: str, **kwargs) -> "CEHCatalogueResource":
        """Factory for JSON-LD format."""
        return cls(dataset_id, format="schema.org", **kwargs)

    @classmethod
    def turtle(cls, dataset_id: str, **kwargs) -> "CEHCatalogueResource":
        """Factory for RDF Turtle format."""
        return cls(dataset_id, format="ttl", **kwargs)


class CEHSupportingDocsResource(HttpResource):
    """
    Resource for fetching supporting documents ZIP from CEH.

    Example:
        resource = CEHSupportingDocsResource("f710bed1-e564-47bf-b82c-4c2a2fe2810e")
        result = await resource.fetch()
        # result.content is the ZIP file bytes
    """

    BASE_URL = "https://data-package.ceh.ac.uk/sd"

    def __init__(
        self,
        dataset_id: str,
        auth: Optional[tuple[str, str]] = None,
        timeout: float = 60.0,  # Longer timeout for downloads
    ):
        """
        Initialize supporting docs resource.

        Args:
            dataset_id: Dataset UUID
            auth: Optional authentication
            timeout: Request timeout (default 60s for larger files)
        """
        self._dataset_id = dataset_id
        url = f"{self.BASE_URL}/{dataset_id}.zip"

        super().__init__(
            url=url,
            auth=auth,
            timeout=timeout,
        )

    @property
    def dataset_id(self) -> str:
        return self._dataset_id