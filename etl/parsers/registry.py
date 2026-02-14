"""
Parser registry for auto-detecting and selecting parsers.

Implements the Strategy pattern - select the right parser based on content.
"""

from typing import Optional

from etl.models import DatasetMetadata

from .base import MetadataParser, ParseError
from .json_parser import CEHJSONParser
from .xml_parser import ISO19115Parser


class ParserRegistry:
    """
    Registry for metadata parsers.

    Auto-detects the appropriate parser based on content type or content.

    Example:
        registry = ParserRegistry()
        parser = registry.get_parser_for_content_type("application/json")
        metadata = parser.parse(content)

        # Or auto-detect:
        metadata = registry.parse(content, content_type="application/json")
    """

    def __init__(self):
        """Initialize registry with default parsers."""
        self._parsers: list[MetadataParser] = [
            CEHJSONParser(),
            ISO19115Parser(),
        ]

    def register(self, parser: MetadataParser) -> None:
        """
        Register a new parser.

        Args:
            parser: Parser instance to register
        """
        self._parsers.append(parser)

    def get_parser_for_content_type(self, content_type: str) -> Optional[MetadataParser]:
        """
        Get parser that can handle the given content type.

        Args:
            content_type: MIME type string

        Returns:
            Matching parser or None
        """
        for parser in self._parsers:
            if parser.can_parse(content_type):
                return parser
        return None

    def get_parser_by_name(self, format_name: str) -> Optional[MetadataParser]:
        """
        Get parser by format name.

        Args:
            format_name: Parser format name (e.g., "ceh_json", "iso19115")

        Returns:
            Matching parser or None
        """
        for parser in self._parsers:
            if parser.format_name == format_name:
                return parser
        return None

    def detect_format(self, content: str) -> Optional[MetadataParser]:
        """
        Auto-detect format from content.

        Args:
            content: Raw content string

        Returns:
            Matching parser or None
        """
        content_stripped = content.strip()

        # JSON detection
        if content_stripped.startswith("{") or content_stripped.startswith("["):
            return self.get_parser_by_name("ceh_json")

        # XML detection
        if content_stripped.startswith("<?xml") or content_stripped.startswith("<"):
            return self.get_parser_by_name("iso19115")

        return None

    def parse(
        self,
        content: str,
        content_type: Optional[str] = None,
        format_name: Optional[str] = None,
    ) -> DatasetMetadata:
        """
        Parse content using the appropriate parser.

        Args:
            content: Raw content string
            content_type: Optional MIME type hint
            format_name: Optional explicit format name

        Returns:
            Parsed DatasetMetadata

        Raises:
            ParseError: If no parser found or parsing fails
        """
        parser = None

        # Try explicit format name first
        if format_name:
            parser = self.get_parser_by_name(format_name)

        # Try content type
        if not parser and content_type:
            parser = self.get_parser_for_content_type(content_type)

        # Try auto-detection
        if not parser:
            parser = self.detect_format(content)

        if not parser:
            raise ParseError(
                f"No parser found for content_type={content_type}, format={format_name}"
            )

        return parser.parse(content)

    @property
    def available_parsers(self) -> list[str]:
        """List available parser format names."""
        return [p.format_name for p in self._parsers]


# Default registry instance
_default_registry: Optional[ParserRegistry] = None


def get_default_registry() -> ParserRegistry:
    """Get or create default parser registry."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ParserRegistry()
    return _default_registry