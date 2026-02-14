"""
Database session management.

Provides session factory and Unit of Work pattern for transaction control.

Architecture:
- SessionFactory: Creates sessions, manages database connection
- UnitOfWork: Transaction boundary that OWNS repositories
- Repositories can work standalone OR through UnitOfWork

Design decisions:
- Sync SQLAlchemy (not async) - SQLite doesn't truly benefit from async
- UnitOfWork owns repositories (not the other way around)
- Standalone repositories for simple read operations
- UnitOfWork for writes and cross-repository transactions
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from etl.models.orm import Base

# Avoid circular imports - repositories import this module
if TYPE_CHECKING:
    from .dataset_repository import DatasetRepository
    from .user_repository import UserRepository
    from .search_history_repository import SearchHistoryRepository


def _enable_sqlite_foreign_keys(dbapi_conn, connection_record):
    """Enable foreign key constraints for SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class DatabaseConfig:
    """Database configuration."""

    def __init__(
        self,
        database_path: str | Path = "data/metadata.db",
        echo: bool = False,
    ):
        """
        Initialize database configuration.

        Args:
            database_path: Path to SQLite database file
            echo: Whether to log SQL statements
        """
        self.database_path = Path(database_path)
        self.echo = echo

    @property
    def connection_string(self) -> str:
        """SQLAlchemy connection string."""
        return f"sqlite:///{self.database_path}"


class SessionFactory:
    """
    Factory for creating database sessions.

    Centralizes session creation and ensures proper configuration.
    This is the single source of database connections in the application.

    Usage:
        factory = SessionFactory(DatabaseConfig())
        factory.init_db()  # Create tables

        # For simple reads - standalone repository
        repo = DatasetRepository(factory)
        dataset = repo.get("abc-123")

        # For writes/transactions - use UnitOfWork
        with UnitOfWork(factory) as uow:
            uow.datasets.save(dataset)
            uow.users.save(user)
            uow.commit()
    """

    def __init__(self, config: DatabaseConfig):
        """
        Initialize session factory.

        Args:
            config: Database configuration
        """
        self.config = config

        # Ensure database directory exists
        self.config.database_path.parent.mkdir(parents=True, exist_ok=True)

        # Create engine
        self._engine = create_engine(
            config.connection_string,
            echo=config.echo,
        )

        # Enable foreign keys for SQLite
        event.listen(self._engine, "connect", _enable_sqlite_foreign_keys)

        # Create session factory
        self._session_factory = sessionmaker(
            bind=self._engine,
            expire_on_commit=False,  # Keep objects usable after commit
        )

    @property
    def engine(self) -> Engine:
        """The SQLAlchemy engine."""
        return self._engine

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self._engine)

    def drop_all(self) -> None:
        """Drop all tables. Use with caution!"""
        Base.metadata.drop_all(self._engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Create a session context manager.

        The session is automatically closed when the context exits.
        Caller is responsible for commit/rollback.

        Usage:
            with factory.session() as session:
                session.add(obj)
                session.commit()
        """
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def create_session(self) -> Session:
        """
        Create a new session (caller manages lifecycle).

        Use session() context manager when possible.
        """
        return self._session_factory()


class UnitOfWork:
    """
    Unit of Work pattern for transaction management.

    The UoW OWNS repositories and provides them through properties.
    All repositories share the same session, ensuring atomic commits.

    Usage:
        with UnitOfWork(session_factory) as uow:
            # Access repositories through UoW
            uow.datasets.save(dataset1)
            uow.datasets.save(dataset2)
            uow.users.save(user)

            uow.commit()  # All changes committed atomically

    If an exception occurs or commit() isn't called, changes are rolled back.

    Patterns:
        # ETL batch processing
        with UnitOfWork(factory) as uow:
            for metadata in all_datasets:
                uow.datasets.save(metadata)
            uow.commit()

        # Web request (save search + update user)
        with UnitOfWork(factory) as uow:
            uow.search_history.save(search)
            uow.users.update_last_active(user_id)
            uow.commit()

        # Rollback on error
        with UnitOfWork(factory) as uow:
            try:
                uow.datasets.save(dataset)
                external_api_call()  # Might fail
                uow.commit()
            except ExternalError:
                uow.rollback()
                raise
    """

    def __init__(self, session_factory: SessionFactory):
        """
        Initialize Unit of Work.

        Args:
            session_factory: Factory for creating sessions
        """
        self._session_factory = session_factory
        self._session: Session | None = None

        # Lazy-initialized repositories
        self._datasets: DatasetRepository | None = None
        self._users: UserRepository | None = None
        self._search_history: SearchHistoryRepository | None = None

    @property
    def session(self) -> Session:
        """The current session."""
        if self._session is None:
            raise RuntimeError("UnitOfWork not entered. Use 'with UnitOfWork(...) as uow:'")
        return self._session

    # =========================================================================
    # Repository Properties (Lazy Initialization)
    # =========================================================================

    @property
    def datasets(self) -> "DatasetRepository":
        """
        Dataset repository (lazy-created).

        All operations use the UoW's shared session.
        """
        if self._datasets is None:
            from .dataset_repository import DatasetRepository
            self._datasets = DatasetRepository(session=self.session)
        return self._datasets

    @property
    def users(self) -> "UserRepository":
        """
        User repository (lazy-created).

        All operations use the UoW's shared session.
        """
        if self._users is None:
            from .user_repository import UserRepository
            self._users = UserRepository(session=self.session)
        return self._users

    @property
    def search_history(self) -> "SearchHistoryRepository":
        """
        Search history repository (lazy-created).

        All operations use the UoW's shared session.
        """
        if self._search_history is None:
            from .search_history_repository import SearchHistoryRepository
            self._search_history = SearchHistoryRepository(session=self.session)
        return self._search_history

    # =========================================================================
    # Context Manager
    # =========================================================================

    def __enter__(self) -> "UnitOfWork":
        """Start the unit of work (create session)."""
        self._session = self._session_factory.create_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        End the unit of work.

        If an exception occurred or commit() wasn't called, rollback.
        Always closes the session.
        """
        if self._session is None:
            return

        try:
            if exc_type is not None:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

            # Clear repository references
            self._datasets = None
            self._users = None
            self._search_history = None

    # =========================================================================
    # Transaction Control
    # =========================================================================

    def commit(self) -> None:
        """Commit the transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the transaction."""
        self.session.rollback()

    def flush(self) -> None:
        """Flush pending changes without committing."""
        self.session.flush()


# =============================================================================
# Convenience Functions
# =============================================================================

_default_session_factory: SessionFactory | None = None


def get_session_factory(
    database_path: str | Path = "data/metadata.db",
    echo: bool = False,
) -> SessionFactory:
    """
    Get or create the default session factory.

    Uses singleton pattern for convenience, but you can always
    create your own SessionFactory for testing or multiple databases.
    """
    global _default_session_factory

    if _default_session_factory is None:
        config = DatabaseConfig(database_path=database_path, echo=echo)
        _default_session_factory = SessionFactory(config)

    return _default_session_factory


def reset_session_factory() -> None:
    """Reset the default session factory (mainly for testing)."""
    global _default_session_factory
    _default_session_factory = None