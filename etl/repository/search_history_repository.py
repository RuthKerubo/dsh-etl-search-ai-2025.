"""
Search history repository implementation.

Provides data access for search history records.
Useful for analytics, personalization, and audit trails.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from etl.models.user import SearchHistoryEntry
from etl.models.orm import SearchHistory as SearchHistoryORM
from .base import Repository

if TYPE_CHECKING:
    from .session import SessionFactory


def _orm_to_domain(record: SearchHistoryORM) -> SearchHistoryEntry:
    """Convert ORM to domain model."""
    return SearchHistoryEntry(
        id=record.id,
        user_id=record.user_id,
        query_text=record.query_text,
        search_type=record.search_type,
        result_count=record.result_count,
        searched_at=record.searched_at,
        duration_ms=record.duration_ms,
    )


def _domain_to_orm(entry: SearchHistoryEntry) -> SearchHistoryORM:
    """Convert domain model to ORM."""
    return SearchHistoryORM(
        id=entry.id,
        user_id=entry.user_id,
        query_text=entry.query_text,
        search_type=entry.search_type,
        result_count=entry.result_count,
        searched_at=entry.searched_at,
        duration_ms=entry.duration_ms,
    )


class SearchHistoryRepository(Repository[SearchHistoryEntry, int]):
    """
    Repository for search history.

    Records and retrieves user search history for:
    - Analytics (popular searches, trends)
    - Personalization (recent searches, suggestions)
    - Audit trails

    Usage:
        # Record a search
        entry = SearchHistoryEntry(
            user_id=user.id,
            query_text="climate data",
            result_count=42,
            duration_ms=150,
        )
        repo.save(entry)

        # Get user's recent searches
        recent = repo.get_user_history(user_id, limit=10)

        # Get popular searches
        popular = repo.get_popular_queries(days=7, limit=20)
    """

    def __init__(
        self,
        session_factory: "SessionFactory | None" = None,
        *,
        session: Session | None = None,
    ):
        """
        Initialize repository.

        Args:
            session_factory: Factory for standalone mode
            session: Existing session for UoW mode
        """
        if session_factory is None and session is None:
            raise ValueError("Must provide either session_factory or session")
        if session_factory is not None and session is not None:
            raise ValueError("Provide session_factory OR session, not both")

        self._session_factory = session_factory
        self._managed_session = session

    def _get_session(self) -> tuple[Session, bool]:
        """Get session and whether to close it."""
        if self._managed_session is not None:
            return self._managed_session, False
        return self._session_factory.create_session(), True

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def get(self, identifier: int) -> SearchHistoryEntry | None:
        """Get search history entry by ID."""
        session, should_close = self._get_session()
        try:
            record = session.query(SearchHistoryORM).filter(
                SearchHistoryORM.id == identifier
            ).first()
            return _orm_to_domain(record) if record else None
        finally:
            if should_close:
                session.close()

    def get_all(self) -> list[SearchHistoryEntry]:
        """Get all search history (use with caution - can be large!)."""
        session, should_close = self._get_session()
        try:
            records = session.query(SearchHistoryORM).order_by(
                desc(SearchHistoryORM.searched_at)
            ).all()
            return [_orm_to_domain(r) for r in records]
        finally:
            if should_close:
                session.close()

    def save(self, entity: SearchHistoryEntry) -> int:
        """Save a search history entry."""
        session, should_close = self._get_session()
        try:
            if entity.id:
                # Update existing (rare for history)
                existing = session.query(SearchHistoryORM).filter(
                    SearchHistoryORM.id == entity.id
                ).first()
                if existing:
                    existing.query_text = entity.query_text
                    existing.search_type = entity.search_type
                    existing.result_count = entity.result_count
                    existing.duration_ms = entity.duration_ms

                    if should_close:
                        session.commit()
                    return entity.id

            # Create new (typical case)
            record = _domain_to_orm(entity)
            session.add(record)

            if should_close:
                session.commit()
            else:
                session.flush()

            return record.id
        except Exception:
            if should_close:
                session.rollback()
            raise
        finally:
            if should_close:
                session.close()

    def delete(self, identifier: int) -> bool:
        """Delete a search history entry."""
        session, should_close = self._get_session()
        try:
            record = session.query(SearchHistoryORM).filter(
                SearchHistoryORM.id == identifier
            ).first()
            if not record:
                return False

            session.delete(record)
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

    def exists(self, identifier: int) -> bool:
        """Check if entry exists."""
        session, should_close = self._get_session()
        try:
            count = session.query(func.count(SearchHistoryORM.id)).filter(
                SearchHistoryORM.id == identifier
            ).scalar()
            return count > 0
        finally:
            if should_close:
                session.close()

    def count(self) -> int:
        """Count total entries."""
        session, should_close = self._get_session()
        try:
            return session.query(func.count(SearchHistoryORM.id)).scalar() or 0
        finally:
            if should_close:
                session.close()

    # =========================================================================
    # Search-Specific Operations
    # =========================================================================

    def record_search(
        self,
        query_text: str,
        result_count: int,
        user_id: Optional[int] = None,
        search_type: str = "semantic",
        duration_ms: Optional[int] = None,
    ) -> SearchHistoryEntry:
        """
        Convenience method to record a search.

        Args:
            query_text: The search query
            result_count: Number of results returned
            user_id: User ID (optional for anonymous)
            search_type: Type of search performed
            duration_ms: Query execution time

        Returns:
            Created SearchHistoryEntry
        """
        entry = SearchHistoryEntry(
            user_id=user_id,
            query_text=query_text,
            search_type=search_type,
            result_count=result_count,
            duration_ms=duration_ms,
        )

        entry_id = self.save(entry)
        entry.id = entry_id
        return entry

    def get_user_history(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SearchHistoryEntry]:
        """
        Get a user's search history.

        Args:
            user_id: User ID
            limit: Maximum entries to return
            offset: Number of entries to skip

        Returns:
            List of search history entries (most recent first)
        """
        session, should_close = self._get_session()
        try:
            records = session.query(SearchHistoryORM).filter(
                SearchHistoryORM.user_id == user_id
            ).order_by(
                desc(SearchHistoryORM.searched_at)
            ).offset(offset).limit(limit).all()

            return [_orm_to_domain(r) for r in records]
        finally:
            if should_close:
                session.close()

    def get_recent_queries(
        self,
        user_id: int,
        limit: int = 5,
    ) -> list[str]:
        """
        Get user's most recent unique queries.

        Useful for search suggestions / autocomplete.

        Args:
            user_id: User ID
            limit: Maximum queries to return

        Returns:
            List of query strings (most recent first, deduplicated)
        """
        session, should_close = self._get_session()
        try:
            # Get recent queries, then deduplicate in Python
            # (SQLite doesn't have good DISTINCT ON support)
            records = session.query(SearchHistoryORM.query_text).filter(
                SearchHistoryORM.user_id == user_id
            ).order_by(
                desc(SearchHistoryORM.searched_at)
            ).limit(limit * 3).all()  # Get more to allow for deduplication

            seen = set()
            unique_queries = []
            for (query,) in records:
                if query.lower() not in seen:
                    seen.add(query.lower())
                    unique_queries.append(query)
                    if len(unique_queries) >= limit:
                        break

            return unique_queries
        finally:
            if should_close:
                session.close()

    def get_popular_queries(
        self,
        days: int = 7,
        limit: int = 20,
    ) -> list[tuple[str, int]]:
        """
        Get most popular search queries.

        Args:
            days: Look back period in days
            limit: Maximum queries to return

        Returns:
            List of (query, count) tuples, sorted by popularity
        """
        session, should_close = self._get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)

            results = session.query(
                SearchHistoryORM.query_text,
                func.count(SearchHistoryORM.id).label('count')
            ).filter(
                SearchHistoryORM.searched_at >= cutoff
            ).group_by(
                func.lower(SearchHistoryORM.query_text)
            ).order_by(
                desc('count')
            ).limit(limit).all()

            return [(query, count) for query, count in results]
        finally:
            if should_close:
                session.close()

    def get_search_stats(
        self,
        days: int = 30,
    ) -> dict:
        """
        Get search statistics for analytics.

        Args:
            days: Look back period

        Returns:
            Dict with statistics
        """
        session, should_close = self._get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)

            # Total searches
            total = session.query(func.count(SearchHistoryORM.id)).filter(
                SearchHistoryORM.searched_at >= cutoff
            ).scalar() or 0

            # Unique users
            unique_users = session.query(
                func.count(func.distinct(SearchHistoryORM.user_id))
            ).filter(
                SearchHistoryORM.searched_at >= cutoff,
                SearchHistoryORM.user_id.isnot(None),
            ).scalar() or 0

            # Average results per search
            avg_results = session.query(
                func.avg(SearchHistoryORM.result_count)
            ).filter(
                SearchHistoryORM.searched_at >= cutoff
            ).scalar() or 0

            # Average duration
            avg_duration = session.query(
                func.avg(SearchHistoryORM.duration_ms)
            ).filter(
                SearchHistoryORM.searched_at >= cutoff,
                SearchHistoryORM.duration_ms.isnot(None),
            ).scalar() or 0

            return {
                "period_days": days,
                "total_searches": total,
                "unique_users": unique_users,
                "avg_results": round(avg_results, 1),
                "avg_duration_ms": round(avg_duration, 1),
            }
        finally:
            if should_close:
                session.close()

    def clear_user_history(self, user_id: int) -> int:
        """
        Clear all search history for a user.

        Args:
            user_id: User ID

        Returns:
            Number of entries deleted
        """
        session, should_close = self._get_session()
        try:
            count = session.query(SearchHistoryORM).filter(
                SearchHistoryORM.user_id == user_id
            ).delete()

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

    def clear_old_history(self, days: int = 90) -> int:
        """
        Clear search history older than specified days.

        Useful for data retention policies.

        Args:
            days: Delete entries older than this

        Returns:
            Number of entries deleted
        """
        session, should_close = self._get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)

            count = session.query(SearchHistoryORM).filter(
                SearchHistoryORM.searched_at < cutoff
            ).delete()

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