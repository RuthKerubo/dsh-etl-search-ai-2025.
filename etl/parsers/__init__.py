"""
Metadata parsers for the ETL pipeline.

Provides parsers for different metadata formats:
- CEH JSON (custom format from catalogue API)
- ISO 19115 XML (UK GEMINI profile)

The registry enables auto-detection and selection of parsers.

Example:
    from etl.parsers import ParserRegistry

    registry = ParserRegistry()
    metadata = registry.parse(content, content_type="application/json")
"""

from .base import MetadataParser, ParseError
from .json_parser import CEHJSONParser
from .xml_parser import ISO19115Parser
from .registry import (
    ParserRegistry,
    get_default_registry,
)


__all__ = [
    # Base
    "MetadataParser",
    "ParseError",
    # Parsers
    "CEHJSONParser",
    "ISO19115Parser",
    # Registry
    "ParserRegistry",
    "get_default_registry",
]