"""
Health Router.

GET /health - Service status check.
"""

from fastapi import APIRouter

from api.dependencies import get_service_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    """
    Health check endpoint.
    
    Returns status of all services:
    - database: SQLite connection
    - vector_store: ChromaDB
    - embedding_service: Cohere API
    - dataset_count: Number of datasets in DB
    - indexed_count: Number of embedded documents
    """
    status = get_service_status()
    
    return {
        "status": "healthy" if status["database"] else "degraded",
        "services": {
            "database": "up" if status["database"] else "down",
            "vector_store": "up" if status["vector_store"] else "down",
            "embedding_service": "up" if status["embedding_service"] else "down",
        },
        "counts": {
            "datasets": status["dataset_count"],
            "indexed": status["indexed_count"],
        },
        "search_mode": "hybrid" if status["vector_store"] else "keyword-only",
    }