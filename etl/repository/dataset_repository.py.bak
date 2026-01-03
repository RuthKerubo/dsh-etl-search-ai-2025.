"""
Dataset repository implementation.

Provides data access for DatasetMetadata domain models.
Hides all SQLAlchemy details behind a clean domain-focused interface.

Key features:
- Works exclusively with domain models (DatasetMetadata)
- Two modes: standalone (SessionFactory) or UoW-managed (Session)
- Supports bulk operations for ETL efficiency
- Text search on title and abstract

Usage Modes:
    1. Standalone (auto-manages sessions per operation):
       repo = DatasetRepository(session_factory)
       dataset = repo.get("abc-123")  # Own session, auto-closed
    
    2. UnitOfWork (shared session for transactions):
       with UnitOfWork(factory) as uow:
           uow.datasets.save(dataset)  # Uses UoW's session
           uow.commit()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload

from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from etl.models.dataset import DatasetMetadata
from etl.models.orm import Dataset, Keyword
from etl.models.converters import (
    domain_to_orm,
    orm_to_domain,
    update_dataset_from_domain,
)
from .base import (
    BulkOperationResult,
    BulkRepository,
    PagedResult,
    SearchableRepository,
)

if TYPE_CHECKING:
    from .session import SessionFactory


class DatasetRepository(SearchableRepository[DatasetMetadata, str], BulkRepository[DatasetMetadata, str]):
    """
    Repository for dataset metadata.
    
    Provides CRUD operations, search, and bulk operations for datasets.
    Works with DatasetMetadata domain models only - SQLAlchemy is hidden.
    
    Two Construction Modes:
        1. With SessionFactory (standalone use):
           repo = DatasetRepository(session_factory)
           # Each operation creates/closes its own session
           
        2. With Session (UnitOfWork use):
           repo = DatasetRepository(session=uow.session)
           # Uses provided session, caller manages lifecycle
    
    The UnitOfWork creates repositories in mode 2 automatically.
    """
    
    @overload
    def __init__(self, session_factory: "SessionFactory", *, eager_load: bool = True) -> None: ...
    
    @overload
    def __init__(self, *, session: Session, eager_load: bool = True) -> None: ...
    
    def __init__(
        self,
        session_factory: "SessionFactory | None" = None,
        *,
        session: Session | None = None,
        eager_load: bool = True,
    ):
        """
        Initialize repository.
        
        Provide EITHER session_factory (standalone mode) OR session (UoW mode).
        
        Args:
            session_factory: Factory for creating sessions (standalone mode)
            session: Existing session to use (UoW mode)
            eager_load: Whether to eagerly load relationships (prevents N+1)
        """
        if session_factory is None and session is None:
            raise ValueError("Must provide either session_factory or session")
        if session_factory is not None and session is not None:
            raise ValueError("Provide session_factory OR session, not both")
        
        self._session_factory = session_factory
        self._managed_session = session  # Session managed externally (UoW)
        self._eager_load = eager_load
    
    def _get_session(self) -> tuple[Session, bool]:
        """
        Get a session for operations.
        
        Returns:
            Tuple of (session, should_close)
            should_close is False for managed sessions (from UoW)
        """
        if self._managed_session is not None:
            return self._managed_session, False
        return self._session_factory.create_session(), True
    
    def _apply_eager_loading(self, query):
        """Apply eager loading options to prevent N+1 queries."""
        if not self._eager_load:
            return query
        
        return query.options(
            joinedload(Dataset.keywords),
            joinedload(Dataset.party_associations),
            joinedload(Dataset.distributions),
            joinedload(Dataset.related_documents),
            joinedload(Dataset.supporting_documents),
            joinedload(Dataset.raw_documents),
        )
    
    # =========================================================================
    # Core CRUD Operations
    # =========================================================================
    
    def get(self, identifier: str) -> DatasetMetadata | None:
        """
        Retrieve a dataset by identifier.
        
        Args:
            identifier: Dataset UUID
            
        Returns:
            DatasetMetadata if found, None otherwise
        """
        session, should_close = self._get_session()
        try:
            query = session.query(Dataset).filter(Dataset.identifier == identifier)
            query = self._apply_eager_loading(query)
            
            dataset = query.first()
            if dataset is None:
                return None
            
            return orm_to_domain(dataset)
        finally:
            if should_close:
                session.close()
    
    def get_all(self) -> list[DatasetMetadata]:
        """
        Retrieve all datasets.
        
        Returns:
            List of all DatasetMetadata
        """
        session, should_close = self._get_session()
        try:
            query = session.query(Dataset)
            query = self._apply_eager_loading(query)
            
            datasets = query.all()
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()
    
    def get_paged(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> PagedResult[DatasetMetadata]:
        """
        Retrieve datasets with pagination.
        
        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            
        Returns:
            PagedResult with items and metadata
        """
        session, should_close = self._get_session()
        try:
            # Get total count
            total = session.query(func.count(Dataset.id)).scalar() or 0
            
            # Get page
            query = session.query(Dataset)
            query = self._apply_eager_loading(query)
            query = query.order_by(Dataset.title)
            query = query.offset((page - 1) * page_size).limit(page_size)
            
            datasets = query.all()
            items = [orm_to_domain(ds) for ds in datasets]
            
            return PagedResult(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
            )
        finally:
            if should_close:
                session.close()
    
    def save(self, entity: DatasetMetadata) -> str:
        """
        Save a dataset (insert or update).
        
        If dataset with same identifier exists, updates it.
        Otherwise, creates new record.
        
        Args:
            entity: DatasetMetadata to save
            
        Returns:
            Identifier of saved dataset
        """
        session, should_close = self._get_session()
        try:
            # Check if exists
            existing = session.query(Dataset).filter(
                Dataset.identifier == entity.identifier
            ).first()
            
            if existing:
                # Update existing
                update_dataset_from_domain(existing, entity, session)
                dataset = existing
            else:
                # Create new
                dataset = domain_to_orm(entity, session)
                session.add(dataset)
            
            # Only commit if we own the session
            if should_close:
                session.commit()
            else:
                session.flush()  # Flush to get ID, but don't commit
            
            return entity.identifier
        except Exception:
            if should_close:
                session.rollback()
            raise
        finally:
            if should_close:
                session.close()
    
    def delete(self, identifier: str) -> bool:
        """
        Delete a dataset by identifier.
        
        Args:
            identifier: Dataset UUID
            
        Returns:
            True if deleted, False if not found
        """
        session, should_close = self._get_session()
        try:
            dataset = session.query(Dataset).filter(
                Dataset.identifier == identifier
            ).first()
            
            if dataset is None:
                return False
            
            session.delete(dataset)
            
            if should_close:
                session.commit()
            
            return True
        except Exception:
            if should_close:
                session.rollback()
            raise
        finally:
            if should_close:
                session.close()
    
    def exists(self, identifier: str) -> bool:
        """
        Check if a dataset exists.
        
        Args:
            identifier: Dataset UUID
            
        Returns:
            True if exists, False otherwise
        """
        session, should_close = self._get_session()
        try:
            count = session.query(func.count(Dataset.id)).filter(
                Dataset.identifier == identifier
            ).scalar()
            return count > 0
        finally:
            if should_close:
                session.close()
    
    def count(self) -> int:
        """
        Count total datasets.
        
        Returns:
            Total count
        """
        session, should_close = self._get_session()
        try:
            return session.query(func.count(Dataset.id)).scalar() or 0
        finally:
            if should_close:
                session.close()
    
    # =========================================================================
    # Search Operations
    # =========================================================================
    
    def search(self, query: str, limit: int = 100) -> list[DatasetMetadata]:
        """
        Search datasets by text query.
        
        Searches in title and abstract using SQL LIKE.
        For semantic search, use the vector store instead.
        
        Args:
            query: Search query string
            limit: Maximum results to return
            
        Returns:
            List of matching DatasetMetadata
        """
        session, should_close = self._get_session()
        try:
            search_pattern = f"%{query}%"
            
            db_query = session.query(Dataset).filter(
                or_(
                    Dataset.title.ilike(search_pattern),
                    Dataset.abstract.ilike(search_pattern),
                )
            )
            db_query = self._apply_eager_loading(db_query)
            db_query = db_query.limit(limit)
            
            datasets = db_query.all()
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()
    
    def search_by_keyword(self, keyword: str, limit: int = 100) -> list[DatasetMetadata]:
        """
        Search datasets by keyword.
        
        Args:
            keyword: Keyword to search for
            limit: Maximum results
            
        Returns:
            List of matching DatasetMetadata
        """
        session, should_close = self._get_session()
        try:
            db_query = session.query(Dataset).join(Dataset.keywords).filter(
                Keyword.keyword.ilike(f"%{keyword}%")
            )
            db_query = self._apply_eager_loading(db_query)
            db_query = db_query.limit(limit)
            
            datasets = db_query.all()
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()
    
    def get_all_identifiers(self) -> list[str]:
        """
        Get all dataset identifiers.
        
        Efficient query that only fetches identifiers, not full records.
        
        Returns:
            List of dataset UUIDs
        """
        session, should_close = self._get_session()
        try:
            results = session.query(Dataset.identifier).all()
            return [r[0] for r in results]
        finally:
            if should_close:
                session.close()
    
    # =========================================================================
    # Bulk Operations
    # =========================================================================
    
    def save_many(self, entities: list[DatasetMetadata]) -> BulkOperationResult:
        """
        Save multiple datasets in a single transaction.
        
        More efficient than calling save() repeatedly.
        Continues on individual failures.
        
        Args:
            entities: List of DatasetMetadata to save
            
        Returns:
            BulkOperationResult with successes and failures
        """
        result = BulkOperationResult()
        session, should_close = self._get_session()
        
        try:
            for entity in entities:
                try:
                    # Check if exists
                    existing = session.query(Dataset).filter(
                        Dataset.identifier == entity.identifier
                    ).first()
                    
                    if existing:
                        update_dataset_from_domain(existing, entity, session)
                    else:
                        dataset = domain_to_orm(entity, session)
                        session.add(dataset)
                    
                    # Flush to catch individual errors
                    session.flush()
                    result.add_success(entity.identifier)
                    
                except Exception as e:
                    # Record failure but continue
                    session.rollback()
                    result.add_failure(entity.identifier, str(e))
            
            # Commit all successful saves
            if should_close and result.success_count > 0:
                session.commit()
            
            return result
            
        finally:
            if should_close:
                session.close()
    
    def delete_many(self, identifiers: list[str]) -> BulkOperationResult:
        """
        Delete multiple datasets in a single transaction.
        
        Args:
            identifiers: List of dataset UUIDs to delete
            
        Returns:
            BulkOperationResult with successes and failures
        """
        result = BulkOperationResult()
        session, should_close = self._get_session()
        
        try:
            for identifier in identifiers:
                try:
                    dataset = session.query(Dataset).filter(
                        Dataset.identifier == identifier
                    ).first()
                    
                    if dataset:
                        session.delete(dataset)
                        session.flush()
                        result.add_success(identifier)
                    else:
                        result.add_failure(identifier, "Not found")
                        
                except Exception as e:
                    session.rollback()
                    result.add_failure(identifier, str(e))
            
            if should_close and result.success_count > 0:
                session.commit()
            
            return result
            
        finally:
            if should_close:
                session.close()
    
    # =========================================================================
    # ETL-Specific Operations
    # =========================================================================
    
    def get_datasets_for_embedding(
        self,
        exclude_embedded: bool = True,
    ) -> list[DatasetMetadata]:
        """
        Get datasets that need embeddings generated.
        
        Args:
            exclude_embedded: If True, exclude datasets that already have embeddings
            
        Returns:
            List of DatasetMetadata needing embeddings
        """
        session, should_close = self._get_session()
        try:
            query = session.query(Dataset)
            
            if exclude_embedded:
                # Left join with embeddings and filter for NULL
                from etl.models.orm import EmbeddingRecord
                query = query.outerjoin(EmbeddingRecord).filter(
                    EmbeddingRecord.id == None
                )
            
            query = self._apply_eager_loading(query)
            datasets = query.all()
            
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()
    
    def get_by_identifiers(self, identifiers: list[str]) -> list[DatasetMetadata]:
        """
        Get multiple datasets by their identifiers.
        
        More efficient than calling get() repeatedly.
        
        Args:
            identifiers: List of dataset UUIDs
            
        Returns:
            List of DatasetMetadata (may be fewer than input if some not found)
        """
        session, should_close = self._get_session()
        try:
            query = session.query(Dataset).filter(
                Dataset.identifier.in_(identifiers)
            )
            query = self._apply_eager_loading(query)
            
            datasets = query.all()
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()
    
    def clear_all(self) -> int:
        """
        Delete all datasets.
        
        Use with caution! Mainly for testing or re-importing.
        
        Returns:
            Number of datasets deleted
        """
        session, should_close = self._get_session()
        try:
            count = session.query(Dataset).count()
            session.query(Dataset).delete()
            
            if should_close:
                session.commit()
            
            return count
        except Exception:
            if should_close:
                session.rollback()
            raise
        finally:
            if should_close:
                session.close()