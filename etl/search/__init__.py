"""
Search services for the dataset discovery application.

Provides hybrid search combining semantic (vector) and keyword (SQL) approaches.
"""

from .hybrid import (
    HybridSearchService,
    HybridSearchResult,
    HybridSearchResponse,
    QueryType,
    hybrid_search,
)

__all__ = [
    "HybridSearchService",
    "HybridSearchResult",
    "HybridSearchResponse",
    "QueryType",
    "hybrid_search",
]