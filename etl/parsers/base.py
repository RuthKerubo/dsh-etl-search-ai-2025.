"""
Abstract base class for metadata parsers.

All parsers convert raw metadata (XML, JSON, etc.) into the unified
DatasetMetadata domain model.
"""

from abc import ABC, abstractmethod
from typing import Optional

from etl.models import DatasetMetadata


class MetadataParser(ABC):
    """
    Abstract base class for metadata parsers.

    Each parser handles one format and produces DatasetMetadata objects.

    Design:
        - Single Responsibility: One parser per format
        - Liskov Substitution: All parsers are interchangeable
        - Open/Closed: Add new formats by creating new parsers

    Example:
        parser = CEHJSONParser()
        metadata = parser.parse(json_string)
    """

    @abstractmethod
    def parse(self, content: str) -> DatasetMetadata:
        """
        Parse raw content into DatasetMetadata.

        Args:
            content: Raw content string (XML, JSON, etc.)

        Returns:
            Parsed DatasetMetadata object

        Raises:
            ParseError: If content cannot be parsed
        """
        pass

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Name of the format this parser handles."""
        pass

    @property
    @abstractmethod
    def supported_content_types(self) -> list[str]:
        """MIME types this parser can handle."""
        pass

    def can_parse(self, content_type: Optional[str]) -> bool:
        """
        Check if this parser can handle the given content type.

        Args:
            content_type: MIME type string

        Returns:
            True if this parser can handle the content type
        """
        if not content_type:
            return False

        content_type_lower = content_type.lower()
        return any(
            ct in content_type_lower
            for ct in self.supported_content_types
        )


class ParseError(Exception):
    """Raised when parsing fails."""

    def __init__(self, message: str, format_name: str = "", raw_error: Optional[Exception] = None):
        self.format_name = format_name
        self.raw_error = raw_error
        super().__init__(f"[{format_name}] {message}" if format_name else message)