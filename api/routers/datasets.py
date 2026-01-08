"""
Datasets Router.

GET /datasets - List datasets with pagination.
GET /datasets/{id} - Get single dataset.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from api.dependencies import DatasetRepoDep
from api.schemas.responses import DatasetResponse, DatasetListResponse, DatasetListItem

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("", response_model=DatasetListResponse)
def list_datasets(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    repo: DatasetRepoDep = None,
) -> DatasetListResponse:
    """
    List datasets with pagination.
    """
    result = repo.get_paged(page=page, page_size=page_size)
    
    items = [
        DatasetListItem(
            identifier=d.identifier,
            title=d.title or "",
            abstract=(d.abstract or "")[:200] + "..." if d.abstract and len(d.abstract) > 200 else (d.abstract or ""),
            keywords=d.keywords[:5] if d.keywords else [],
        )
        for d in result.items
    ]
    
    return DatasetListResponse(
        items=items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
    )


@router.get("/{identifier}", response_model=DatasetResponse)
def get_dataset(
    identifier: str,
    repo: DatasetRepoDep = None,
) -> DatasetResponse:
    """
    Get a single dataset by identifier.
    """
    dataset = repo.get(identifier, strategy="full")
    
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return DatasetResponse(
        identifier=dataset.identifier,
        title=dataset.title or "",
        abstract=dataset.abstract or "",
        keywords=dataset.keywords,
        lineage=dataset.lineage,
        topic_categories=[tc.value if hasattr(tc, 'value') else tc for tc in dataset.topic_categories],
        bounding_box={
            "west": dataset.bounding_box.west,
            "east": dataset.bounding_box.east,
            "south": dataset.bounding_box.south,
            "north": dataset.bounding_box.north,
        } if dataset.bounding_box else None,
        temporal_extent={
            "start": str(dataset.temporal_extent.start_date) if dataset.temporal_extent and dataset.temporal_extent.start_date else None,
            "end": str(dataset.temporal_extent.end_date) if dataset.temporal_extent and dataset.temporal_extent.end_date else None,
        } if dataset.temporal_extent else None,
    )