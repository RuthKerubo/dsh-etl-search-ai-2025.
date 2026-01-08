"""
Pydantic response models for API endpoints.
"""

from pydantic import BaseModel
from typing import Optional


# =============================================================================
# Dataset Responses
# =============================================================================

class DatasetListItem(BaseModel):
    """Dataset item for list view."""
    identifier: str
    title: str
    abstract: str
    keywords: list[str] = []


class DatasetListResponse(BaseModel):
    """Paginated dataset list."""
    items: list[DatasetListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class DatasetResponse(BaseModel):
    """Full dataset details."""
    identifier: str
    title: str
    abstract: str
    keywords: list[str] = []
    lineage: Optional[str] = None
    topic_categories: list[str] = []
    bounding_box: Optional[dict] = None
    temporal_extent: Optional[dict] = None


# =============================================================================
# Search Responses
# =============================================================================

class SearchResultItem(BaseModel):
    """Single search result."""
    identifier: str
    title: str
    abstract: str
    score: float
    keywords: list[str] = []
    from_semantic: bool = False
    from_keyword: bool = False
    semantic_rank: Optional[int] = None
    keyword_rank: Optional[int] = None


class SearchResponse(BaseModel):
    """Search results with metadata."""
    query: str
    results: list[SearchResultItem]
    total: int
    mode: str  # "hybrid", "semantic", "keyword"
    query_type: str
    semantic_results: int = 0
    keyword_results: int = 0
    duration_ms: float


# =============================================================================
# Health Response
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    services: dict
    counts: dict
    search_mode: str