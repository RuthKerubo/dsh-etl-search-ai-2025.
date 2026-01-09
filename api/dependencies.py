"""
FastAPI Dependencies.

Dependency injection factories for repositories, stores, and services.
Uses lifespan-scoped singletons for expensive resources.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Optional

from dotenv import load_dotenv
load_dotenv()  
from fastapi import Depends

from etl.embeddings.vector_store import VectorStore
from etl.repository.dataset_repository import DatasetRepository
from etl.repository.session import SessionFactory
from etl.search.hybrid import HybridSearchService

# Will be set during app lifespan
_session_factory: Optional["SessionFactory"] = None
_vector_store: Optional["VectorStore"] = None
_embedding_service: Optional["CohereEmbeddingService"] = None
_hybrid_search: Optional["HybridSearchService"] = None


# =============================================================================
# Configuration
# =============================================================================


def get_settings() -> dict:
    """Get application settings."""
    return {
        "database_path": os.getenv("DATABASE_PATH", "data/metadata.db"),
        "chroma_path": os.getenv("CHROMA_PATH", "data/chroma"),
        "cohere_api_key": os.getenv("COHERE_API_KEY"),
    }


# =============================================================================
# Initialization (called from lifespan)
# =============================================================================

def init_dependencies():
    """
    Initialize all dependencies.
    
    Called once during app startup via lifespan.
    """
    global _session_factory, _vector_store, _embedding_service, _hybrid_search
    
    settings = get_settings()
    
    # Database
    from etl.repository import SessionFactory, DatabaseConfig
    
    db_path = settings["database_path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    _session_factory = SessionFactory(DatabaseConfig(database_path=db_path))
    _session_factory.init_db()
    
    # Embedding service (optional)
    api_key = settings["cohere_api_key"]
    if api_key:
        try:
            from etl.embeddings import CohereEmbeddingService
            _embedding_service = CohereEmbeddingService(api_key=api_key)
        except Exception as e:
            print(f"⚠️ Failed to init embedding service: {e}")
            _embedding_service = None
    
    # Vector store (optional, requires embedding service)
    chroma_path = settings["chroma_path"]
    if _embedding_service and Path(chroma_path).exists():
        try:
            from etl.embeddings import VectorStore
            _vector_store = VectorStore(
                embedding_service=_embedding_service,
                persist_path=chroma_path,
            )
        except Exception as e:
            print(f"⚠️ Failed to init vector store: {e}")
            _vector_store = None
    
    # Hybrid search (uses whatever is available)
    from etl.repository import DatasetRepository
    
    if _vector_store:
        from etl.search import HybridSearchService
        _hybrid_search = HybridSearchService(
            vector_store=_vector_store,
            repository=DatasetRepository(_session_factory),
        )


def shutdown_dependencies():
    """
    Cleanup dependencies.
    
    Called during app shutdown via lifespan.
    """
    global _session_factory, _vector_store, _embedding_service, _hybrid_search
    
    _hybrid_search = None
    _vector_store = None
    _embedding_service = None
    _session_factory = None


# =============================================================================
# Dependency Getters
# =============================================================================

def get_session_factory() -> "SessionFactory":
    """Get database session factory."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized")
    return _session_factory


def get_dataset_repository() -> "DatasetRepository":
    """Get dataset repository instance."""
    from etl.repository import DatasetRepository
    return DatasetRepository(get_session_factory())


def get_vector_store() -> Optional["VectorStore"]:
    """Get vector store (None if not configured)."""
    return _vector_store


def get_embedding_service() -> Optional["CohereEmbeddingService"]:
    """Get embedding service (None if not configured)."""
    return _embedding_service


def get_hybrid_search() -> Optional["HybridSearchService"]:
    """Get hybrid search service (None if not configured)."""
    return _hybrid_search


# =============================================================================
# Status Helpers
# =============================================================================

def get_service_status() -> dict:
    """Get status of all services."""
    from etl.repository import DatasetRepository
    
    status = {
        "database": _session_factory is not None,
        "vector_store": _vector_store is not None,
        "embedding_service": _embedding_service is not None,
        "dataset_count": 0,
        "indexed_count": 0,
    }
    
    if _session_factory:
        try:
            repo = DatasetRepository(_session_factory)
            status["dataset_count"] = repo.count()
        except Exception:
            pass
    
    if _vector_store:
        try:
            status["indexed_count"] = len(_vector_store.get_indexed_ids())
        except Exception:
            pass
    
    return status


# =============================================================================
# Type Aliases for Depends()
# =============================================================================

SessionFactoryDep = Annotated["SessionFactory", Depends(get_session_factory)]
DatasetRepoDep = Annotated["DatasetRepository", Depends(get_dataset_repository)]
VectorStoreDep = Annotated[Optional["VectorStore"], Depends(get_vector_store)]
HybridSearchDep = Annotated[Optional["HybridSearchService"], Depends(get_hybrid_search)]