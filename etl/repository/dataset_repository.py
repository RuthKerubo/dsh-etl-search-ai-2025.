"""
Dataset repository implementation - Optimized version.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, overload, Literal

from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload, load_only

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


# Loading strategies
LoadStrategy = Literal["minimal", "standard", "full"]


class DatasetRepository(SearchableRepository[DatasetMetadata, str], BulkRepository[DatasetMetadata, str]):
    """
    Repository for dataset metadata.

    Optimized with different loading strategies:
    - minimal: Just core fields (id, title, abstract) - fast
    - standard: Core + keywords - balanced
    - full: Everything including raw documents - slow
    """

    @overload
    def __init__(self, session_factory: "SessionFactory") -> None: ...

    @overload
    def __init__(self, *, session: Session) -> None: ...

    def __init__(
        self,
        session_factory: "SessionFactory | None" = None,
        *,
        session: Session | None = None,
    ):
        if session_factory is None and session is None:
            raise ValueError("Must provide either session_factory or session")
        if session_factory is not None and session is not None:
            raise ValueError("Provide session_factory OR session, not both")

        self._session_factory = session_factory
        self._managed_session = session

    def _get_session(self) -> tuple[Session, bool]:
        """Get session. Returns (session, should_close)."""
        if self._managed_session is not None:
            return self._managed_session, False
        return self._session_factory.create_session(), True

    def _apply_loading_strategy(self, query, strategy: LoadStrategy = "standard"):
        """Apply loading strategy to query."""
        if strategy == "minimal":
            # No eager loading - just the dataset table
            return query

        elif strategy == "standard":
            # Load keywords only (needed for search display)
            return query.options(
                joinedload(Dataset.keywords),
            )

        elif strategy == "full":
            # Load everything (expensive!)
            return query.options(
                joinedload(Dataset.keywords),
                joinedload(Dataset.party_associations),
                joinedload(Dataset.distributions),
                joinedload(Dataset.related_documents),
                joinedload(Dataset.supporting_documents),
                joinedload(Dataset.raw_documents),
            )

        return query

    # =========================================================================
    # Core CRUD Operations
    # =========================================================================

    def get(self, identifier: str, strategy: LoadStrategy = "standard") -> DatasetMetadata | None:
        """Retrieve a dataset by identifier."""
        session, should_close = self._get_session()
        try:
            query = session.query(Dataset).filter(Dataset.identifier == identifier)
            query = self._apply_loading_strategy(query, strategy)

            dataset = query.first()
            if dataset is None:
                return None

            return orm_to_domain(dataset)
        finally:
            if should_close:
                session.close()

    def get_all(self, strategy: LoadStrategy = "minimal") -> list[DatasetMetadata]:
        """
        Retrieve all datasets.

        Default uses minimal loading for performance.
        """
        session, should_close = self._get_session()
        try:
            query = session.query(Dataset)
            query = self._apply_loading_strategy(query, strategy)

            datasets = query.all()
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()

    def get_all_for_embedding(self) -> list[DatasetMetadata]:
        """
        Get datasets optimized for embedding generation.

        Only loads fields needed for embeddings: identifier, title, abstract.
        Much faster than get_all().
        """
        session, should_close = self._get_session()
        try:
            # Only load columns we need
            query = session.query(Dataset).options(
                load_only(
                    Dataset.identifier,
                    Dataset.title,
                    Dataset.abstract,
                )
            )

            datasets = query.all()

            # Create minimal domain objects
            return [
                DatasetMetadata(
                    identifier=ds.identifier,
                    title=ds.title or "",
                    abstract=ds.abstract or "",
                    keywords=[],  # Not needed for embedding
                )
                for ds in datasets
            ]
        finally:
            if should_close:
                session.close()

    def get_paged(
        self,
        page: int = 1,
        page_size: int = 20,
        strategy: LoadStrategy = "standard",
    ) -> PagedResult[DatasetMetadata]:
        """Retrieve datasets with pagination."""
        session, should_close = self._get_session()
        try:
            total = session.query(func.count(Dataset.id)).scalar() or 0

            query = session.query(Dataset)
            query = self._apply_loading_strategy(query, strategy)
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
        """Save a dataset (insert or update)."""
        session, should_close = self._get_session()
        try:
            existing = session.query(Dataset).filter(
                Dataset.identifier == entity.identifier
            ).first()

            if existing:
                update_dataset_from_domain(existing, entity, session)
            else:
                dataset = domain_to_orm(entity, session)
                session.add(dataset)

            if should_close:
                session.commit()
            else:
                session.flush()

            return entity.identifier
        except Exception:
            if should_close:
                session.rollback()
            raise
        finally:
            if should_close:
                session.close()

    def delete(self, identifier: str) -> bool:
        """Delete a dataset by identifier."""
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
        """Check if a dataset exists."""
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
        """Count total datasets."""
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
        """Search datasets by text query."""
        session, should_close = self._get_session()
        try:
            search_pattern = f"%{query}%"

            db_query = session.query(Dataset).filter(
                or_(
                    Dataset.title.ilike(search_pattern),
                    Dataset.abstract.ilike(search_pattern),
                )
            )
            db_query = self._apply_loading_strategy(db_query, "standard")
            db_query = db_query.limit(limit)

            datasets = db_query.all()
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()

    def search_by_keyword(self, keyword: str, limit: int = 100) -> list[DatasetMetadata]:
        """Search datasets by keyword."""
        session, should_close = self._get_session()
        try:
            db_query = session.query(Dataset).join(Dataset.keywords).filter(
                Keyword.keyword.ilike(f"%{keyword}%")
            )
            db_query = self._apply_loading_strategy(db_query, "standard")
            db_query = db_query.limit(limit)

            datasets = db_query.all()
            return [orm_to_domain(ds) for ds in datasets]
        finally:
            if should_close:
                session.close()

    def get_all_identifiers(self) -> list[str]:
        """Get all dataset identifiers (efficient)."""
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
        """Save multiple datasets in a single transaction."""
        result = BulkOperationResult()
        session, should_close = self._get_session()

        try:
            for entity in entities:
                try:
                    existing = session.query(Dataset).filter(
                        Dataset.identifier == entity.identifier
                    ).first()

                    if existing:
                        update_dataset_from_domain(existing, entity, session)
                    else:
                        dataset = domain_to_orm(entity, session)
                        session.add(dataset)

                    session.flush()
                    result.add_success(entity.identifier)

                except Exception as e:
                    session.rollback()
                    result.add_failure(entity.identifier, str(e))

            if should_close and result.success_count > 0:
                session.commit()

            return result

        finally:
            if should_close:
                session.close()

    def delete_many(self, identifiers: list[str]) -> BulkOperationResult:
        """Delete multiple datasets in a single transaction."""
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

    def clear_all(self) -> int:
        """Delete all datasets."""
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