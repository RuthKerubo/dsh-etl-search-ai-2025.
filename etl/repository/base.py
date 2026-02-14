"""
Abstract base classes for repositories.

Defines the interface that all repositories must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, TypeVar, Optional

# Type variables for generic repository
T = TypeVar("T")  # Entity type (domain model)
ID = TypeVar("ID")  # Identifier type (str, int, etc.)


@dataclass
class PagedResult(Generic[T]):
    """Result of a paginated query."""
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1


@dataclass
class BulkOperationResult:
    """Result of a bulk operation (save_many, delete_many)."""
    succeeded: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (id, error)

    def add_success(self, identifier: str) -> None:
        """Record a successful operation."""
        self.succeeded.append(identifier)

    def add_failure(self, identifier: str, error: str) -> None:
        """Record a failed operation."""
        self.failed.append((identifier, error))

    @property
    def success_count(self) -> int:
        return len(self.succeeded)

    @property
    def failure_count(self) -> int:
        return len(self.failed)

    @property
    def total_count(self) -> int:
        return self.success_count + self.failure_count

    @property
    def all_succeeded(self) -> bool:
        return self.failure_count == 0


class Repository(ABC, Generic[T, ID]):
    """
    Abstract base repository.

    Defines the standard CRUD interface that all repositories implement.
    Works with domain models only — ORM details are hidden in implementations.
    """

    @abstractmethod
    def get(self, identifier: ID) -> Optional[T]:
        """Get entity by identifier."""
        pass

    @abstractmethod
    def get_all(self) -> list[T]:
        """Get all entities."""
        pass

    @abstractmethod
    def save(self, entity: T) -> ID:
        """Save entity (insert or update)."""
        pass

    @abstractmethod
    def delete(self, identifier: ID) -> bool:
        """Delete entity by identifier. Returns True if deleted."""
        pass

    @abstractmethod
    def exists(self, identifier: ID) -> bool:
        """Check if entity exists."""
        pass

    @abstractmethod
    def count(self) -> int:
        """Count total entities."""
        pass


class SearchableRepository(Repository[T, ID], Generic[T, ID]):
    """Repository with search capabilities."""

    @abstractmethod
    def search(self, query: str, limit: int = 100) -> list[T]:
        """Search entities by text query."""
        pass


class BulkRepository(Repository[T, ID], Generic[T, ID]):
    """Repository with bulk operation support."""

    @abstractmethod
    def save_many(self, entities: list[T]) -> BulkOperationResult:
        """Save multiple entities."""
        pass

    @abstractmethod
    def delete_many(self, identifiers: list[ID]) -> BulkOperationResult:
        """Delete multiple entities."""
        pass