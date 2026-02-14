"""
Local filesystem resource implementations.

Provides resources for reading from local files and ZIP archives.
"""

import mimetypes
import os
import zipfile
from datetime import datetime
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


class LocalFileResource(Resource):
    """
    Resource that reads from local filesystem.

    Provides async file reading with proper error handling
    and metadata extraction.

    Attributes:
        path: Path to the local file

    Example:
        resource = LocalFileResource("./data/cache/metadata.json")
        result = await resource.fetch()
        data = json.loads(result.text)
    """

    def __init__(self, path: str | Path):
        """
        Initialize local file resource.

        Args:
            path: Path to the file (string or Path object)
        """
        self._path = Path(path).resolve()

    @property
    def identifier(self) -> str:
        """Absolute path as identifier."""
        return str(self._path)

    @property
    def resource_type(self) -> ResourceType:
        return ResourceType.LOCAL_FILE

    @property
    def path(self) -> Path:
        """The file path."""
        return self._path

    async def exists(self) -> bool:
        """Check if file exists and is readable."""
        try:
            return await aiofiles.os.path.isfile(self._path)
        except Exception:
            return False

    async def _do_fetch(self) -> FetchResult:
        """Read file contents."""
        try:
            async with aiofiles.open(self._path, "rb") as f:
                content = await f.read()

            metadata = await self._get_file_metadata()

            return FetchResult(
                content=content,
                metadata=metadata,
                success=True,
            )

        except FileNotFoundError:
            return FetchResult.failure(f"File not found: {self._path}")
        except PermissionError:
            return FetchResult.failure(f"Permission denied: {self._path}")
        except Exception as e:
            return FetchResult.failure(f"Error reading file: {str(e)}")

    async def _get_file_metadata(self) -> ResourceMetadata:
        """Extract metadata from file."""
        try:
            stat = await aiofiles.os.stat(self._path)

            # Guess content type from extension
            content_type, encoding = mimetypes.guess_type(str(self._path))

            return ResourceMetadata(
                content_type=content_type,
                size_bytes=stat.st_size,
                last_modified=datetime.fromtimestamp(stat.st_mtime),
                encoding=encoding,
                extra={
                    "path": str(self._path),
                    "filename": self._path.name,
                },
            )
        except Exception:
            return ResourceMetadata()

    async def get_metadata(self) -> ResourceMetadata:
        """Get metadata without reading full content."""
        return await self._get_file_metadata()


class ZipEntryResource(Resource):
    """
    Resource that reads a file from within a ZIP archive.

    Allows accessing individual files inside ZIP archives
    without extracting the entire archive.

    Attributes:
        zip_path: Path to the ZIP file
        entry_name: Name of the file inside the ZIP

    Example:
        resource = ZipEntryResource(
            "./data/supporting_docs.zip",
            "readme.pdf"
        )
        result = await resource.fetch()
        pdf_bytes = result.content
    """

    def __init__(self, zip_path: str | Path, entry_name: str):
        """
        Initialize ZIP entry resource.

        Args:
            zip_path: Path to the ZIP archive
            entry_name: Name/path of the entry inside the ZIP
        """
        self._zip_path = Path(zip_path).resolve()
        self._entry_name = entry_name

    @property
    def identifier(self) -> str:
        """Combined path as identifier."""
        return f"zip://{self._zip_path}#{self._entry_name}"

    @property
    def resource_type(self) -> ResourceType:
        return ResourceType.ZIP_ENTRY

    @property
    def zip_path(self) -> Path:
        """Path to the ZIP file."""
        return self._zip_path

    @property
    def entry_name(self) -> str:
        """Name of the entry inside the ZIP."""
        return self._entry_name

    async def exists(self) -> bool:
        """Check if ZIP exists and contains the entry."""
        try:
            if not await aiofiles.os.path.isfile(self._zip_path):
                return False

            # Check if entry exists in ZIP
            # Note: zipfile doesn't have async support, but reading
            # the central directory is fast
            with zipfile.ZipFile(self._zip_path, "r") as zf:
                return self._entry_name in zf.namelist()
        except Exception:
            return False

    async def _do_fetch(self) -> FetchResult:
        """Read entry from ZIP archive."""
        try:
            # zipfile doesn't support async, but extraction is typically fast
            with zipfile.ZipFile(self._zip_path, "r") as zf:
                # Check if entry exists
                if self._entry_name not in zf.namelist():
                    return FetchResult.failure(
                        f"Entry not found in ZIP: {self._entry_name}"
                    )

                # Get entry info for metadata
                info = zf.getinfo(self._entry_name)

                # Read content
                content = zf.read(self._entry_name)

                # Build metadata
                metadata = self._build_metadata(info)

                return FetchResult(
                    content=content,
                    metadata=metadata,
                    success=True,
                )

        except zipfile.BadZipFile:
            return FetchResult.failure(f"Invalid ZIP file: {self._zip_path}")
        except Exception as e:
            return FetchResult.failure(f"Error reading ZIP entry: {str(e)}")

    def _build_metadata(self, info: zipfile.ZipInfo) -> ResourceMetadata:
        """Build metadata from ZIP entry info."""
        # Guess content type from filename
        content_type, encoding = mimetypes.guess_type(self._entry_name)

        # Parse modification time
        try:
            last_modified = datetime(*info.date_time)
        except (ValueError, TypeError):
            last_modified = None

        return ResourceMetadata(
            content_type=content_type,
            size_bytes=info.file_size,
            last_modified=last_modified,
            encoding=encoding,
            extra={
                "zip_path": str(self._zip_path),
                "entry_name": self._entry_name,
                "compressed_size": info.compress_size,
                "compression_type": info.compress_type,
            },
        )

    @classmethod
    def list_entries(cls, zip_path: str | Path) -> list[str]:
        """
        List all entries in a ZIP archive.

        Args:
            zip_path: Path to the ZIP file

        Returns:
            List of entry names
        """
        with zipfile.ZipFile(zip_path, "r") as zf:
            return zf.namelist()

    @classmethod
    def from_zip(
        cls,
        zip_path: str | Path,
        filter_func: Optional[callable] = None,
    ) -> list["ZipEntryResource"]:
        """
        Create resources for all entries in a ZIP.

        Args:
            zip_path: Path to the ZIP file
            filter_func: Optional function to filter entries
                         (receives entry name, returns bool)

        Returns:
            List of ZipEntryResource instances
        """
        entries = cls.list_entries(zip_path)

        if filter_func:
            entries = [e for e in entries if filter_func(e)]

        return [cls(zip_path, entry) for entry in entries]


async def extract_zip_to_directory(
    zip_path: str | Path,
    output_dir: str | Path,
    filter_func: Optional[callable] = None,
) -> list[Path]:
    """
    Extract ZIP contents to a directory.

    Args:
        zip_path: Path to the ZIP file
        output_dir: Directory to extract to
        filter_func: Optional function to filter entries

    Returns:
        List of extracted file paths
    """
    zip_path = Path(zip_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extracted = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for entry in zf.namelist():
            # Skip directories
            if entry.endswith("/"):
                continue

            # Apply filter
            if filter_func and not filter_func(entry):
                continue

            # Extract
            target_path = output_dir / entry
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with zf.open(entry) as src:
                async with aiofiles.open(target_path, "wb") as dst:
                    await dst.write(src.read())

            extracted.append(target_path)

    return extracted