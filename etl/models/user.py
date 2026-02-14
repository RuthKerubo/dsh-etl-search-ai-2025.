"""
User domain models.

These are the domain models for user-related entities.
Separate from ORM models — these represent business logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class UserPreferences(BaseModel):
    """User preferences stored as JSON."""
    theme: str = "light"
    results_per_page: int = 20
    default_search_type: str = "semantic"

    class Config:
        extra = "allow"  # Allow additional preferences


class UserCreate(BaseModel):
    """Data required to create a new user."""
    email: EmailStr
    password: str
    display_name: Optional[str] = None


class UserUpdate(BaseModel):
    """Data for updating a user."""
    display_name: Optional[str] = None
    preferences: Optional[UserPreferences] = None


@dataclass
class User:
    """
    User domain model.

    Represents a user account in the system.
    """
    email: str
    password_hash: str
    id: Optional[int] = None
    display_name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    preferences: UserPreferences = field(default_factory=UserPreferences)

    @property
    def display(self) -> str:
        """Display name or email."""
        return self.display_name or self.email.split("@")[0]


@dataclass
class SearchHistoryEntry:
    """
    Search history entry.

    Records a single search performed by a user.
    """
    query_text: str
    result_count: int
    id: Optional[int] = None
    user_id: Optional[int] = None  # None for anonymous searches
    search_type: str = "semantic"
    searched_at: datetime = field(default_factory=datetime.utcnow)
    duration_ms: Optional[int] = None