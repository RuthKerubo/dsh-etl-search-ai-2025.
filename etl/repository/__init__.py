"""
Repository layer for data access.

This layer provides a clean interface for database operations,
hiding SQLAlchemy implementation details from the rest of the application.

Architecture:
    ┌─────────────────────────────────────────────────────────────────────┐
    │                          UnitOfWork                                 │
    │                                                                     │
    │  Owns: Session (single transaction boundary)                        │
    │  Provides: .datasets, .users, .search_history                       │
    │  Controls: commit(), rollback()                                     │
    └─────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
    DatasetRepository       UserRepository       SearchHistoryRepository

Key components:
    - SessionFactory: Creates and manages database sessions
    - UnitOfWork: Transaction boundary that OWNS repositories
    - DatasetRepository: CRUD and search for datasets
    - UserRepository: User accounts with authentication
    - SearchHistoryRepository: Search analytics and history

Design Principles:
    - Repositories work with domain models only (not ORM models)
    - Two modes: standalone (per-operation sessions) or UoW (shared transaction)
    - UnitOfWork owns repositories for atomic cross-repo operations

Usage Examples:

    # Setup
    from etl.repository import (
        SessionFactory,
        DatabaseConfig,
        DatasetRepository,
        UnitOfWork,
    )

    config = DatabaseConfig(database_path="data/metadata.db")
    session_factory = SessionFactory(config)
    session_factory.init_db()

    # Simple reads (standalone mode)
    repo = DatasetRepository(session_factory)
    dataset = repo.get("abc-123")
    results = repo.search("climate")

    # Writes with transaction (UoW mode)
    with UnitOfWork(session_factory) as uow:
        uow.datasets.save(dataset1)
        uow.datasets.save(dataset2)
        uow.users.save(user)
        uow.search_history.record_search("query", result_count=42)
        uow.commit()  # All or nothing
"""

from .base import (
    BulkOperationResult,
    BulkRepository,
    PagedResult,
    Repository,
    SearchableRepository,
)
from .session import (
    DatabaseConfig,
    SessionFactory,
    UnitOfWork,
    get_session_factory,
    reset_session_factory,
)
from .dataset_repository import DatasetRepository
from .user_repository import UserRepository
from .search_history_repository import SearchHistoryRepository


__all__ = [
    # Base classes
    "Repository",
    "SearchableRepository",
    "BulkRepository",
    "BulkOperationResult",
    "PagedResult",

    # Session management
    "DatabaseConfig",
    "SessionFactory",
    "UnitOfWork",
    "get_session_factory",
    "reset_session_factory",

    # Concrete repositories
    "DatasetRepository",
    "UserRepository",
    "SearchHistoryRepository",
]