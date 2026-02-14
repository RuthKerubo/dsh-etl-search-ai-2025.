"""
User repository implementation.

Provides data access for User domain models.
Handles password hashing and user account management.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from etl.models.user import User, UserCreate, UserPreferences
from etl.models.orm import User as UserORM
from .base import Repository, BulkOperationResult

if TYPE_CHECKING:
    from .session import SessionFactory

import json


def _hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Hash a password using PBKDF2.

    Returns:
        Tuple of (hash, salt)
    """
    if salt is None:
        salt = secrets.token_hex(16)

    # Use PBKDF2 with SHA-256
    hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )

    return hash_bytes.hex(), salt


def _verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash."""
    # Hash format: salt$hash
    try:
        salt, hash_value = stored_hash.split('$')
        computed_hash, _ = _hash_password(password, salt)
        return secrets.compare_digest(computed_hash, hash_value)
    except ValueError:
        return False


def _orm_to_domain(user: UserORM) -> User:
    """Convert ORM User to domain User."""
    preferences = UserPreferences()
    if user.preferences:
        try:
            prefs_dict = json.loads(user.preferences)
            preferences = UserPreferences(**prefs_dict)
        except (json.JSONDecodeError, TypeError):
            pass

    return User(
        id=user.id,
        email=user.email,
        password_hash=user.password_hash,
        display_name=user.display_name,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        last_login=user.last_login,
        preferences=preferences,
    )


def _domain_to_orm(user: User) -> UserORM:
    """Convert domain User to ORM User."""
    return UserORM(
        id=user.id,
        email=user.email,
        password_hash=user.password_hash,
        display_name=user.display_name,
        is_active=user.is_active,
        is_admin=user.is_admin,
        created_at=user.created_at,
        last_login=user.last_login,
        preferences=json.dumps(user.preferences.model_dump()) if user.preferences else None,
    )


class UserRepository(Repository[User, int]):
    """
    Repository for user accounts.

    Handles CRUD operations and authentication-related queries.
    Passwords are hashed before storage.

    Usage:
        # Standalone
        repo = UserRepository(session_factory)

        # With UnitOfWork
        with UnitOfWork(factory) as uow:
            uow.users.create(UserCreate(email="...", password="..."))
            uow.commit()
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

    def get(self, identifier: int) -> User | None:
        """Get user by ID."""
        session, should_close = self._get_session()
        try:
            user = session.query(UserORM).filter(UserORM.id == identifier).first()
            return _orm_to_domain(user) if user else None
        finally:
            if should_close:
                session.close()

    def get_by_email(self, email: str) -> User | None:
        """Get user by email address."""
        session, should_close = self._get_session()
        try:
            user = session.query(UserORM).filter(
                UserORM.email == email.lower()
            ).first()
            return _orm_to_domain(user) if user else None
        finally:
            if should_close:
                session.close()

    def get_all(self) -> list[User]:
        """Get all users."""
        session, should_close = self._get_session()
        try:
            users = session.query(UserORM).all()
            return [_orm_to_domain(u) for u in users]
        finally:
            if should_close:
                session.close()

    def save(self, entity: User) -> int:
        """
        Save a user (insert or update).

        Note: For creating new users, prefer create() which handles password hashing.
        """
        session, should_close = self._get_session()
        try:
            if entity.id:
                # Update existing
                existing = session.query(UserORM).filter(UserORM.id == entity.id).first()
                if existing:
                    existing.email = entity.email.lower()
                    existing.password_hash = entity.password_hash
                    existing.display_name = entity.display_name
                    existing.is_active = entity.is_active
                    existing.is_admin = entity.is_admin
                    existing.last_login = entity.last_login
                    existing.preferences = json.dumps(entity.preferences.model_dump())

                    if should_close:
                        session.commit()
                    return entity.id

            # Create new
            user_orm = _domain_to_orm(entity)
            user_orm.email = user_orm.email.lower()
            session.add(user_orm)

            if should_close:
                session.commit()
            else:
                session.flush()

            return user_orm.id
        except Exception:
            if should_close:
                session.rollback()
            raise
        finally:
            if should_close:
                session.close()

    def delete(self, identifier: int) -> bool:
        """Delete a user by ID."""
        session, should_close = self._get_session()
        try:
            user = session.query(UserORM).filter(UserORM.id == identifier).first()
            if not user:
                return False

            session.delete(user)
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
        """Check if user exists."""
        session, should_close = self._get_session()
        try:
            count = session.query(func.count(UserORM.id)).filter(
                UserORM.id == identifier
            ).scalar()
            return count > 0
        finally:
            if should_close:
                session.close()

    def count(self) -> int:
        """Count total users."""
        session, should_close = self._get_session()
        try:
            return session.query(func.count(UserORM.id)).scalar() or 0
        finally:
            if should_close:
                session.close()

    # =========================================================================
    # User-Specific Operations
    # =========================================================================

    def create(self, data: UserCreate) -> User:
        """
        Create a new user with password hashing.

        Args:
            data: User creation data with plaintext password

        Returns:
            Created User with hashed password
        """
        # Hash the password
        hash_value, salt = _hash_password(data.password)
        password_hash = f"{salt}${hash_value}"

        user = User(
            email=data.email.lower(),
            password_hash=password_hash,
            display_name=data.display_name,
        )

        user_id = self.save(user)
        user.id = user_id
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        """
        Authenticate a user by email and password.

        Args:
            email: User's email
            password: Plaintext password

        Returns:
            User if authentication successful, None otherwise
        """
        user = self.get_by_email(email)
        if not user:
            return None

        if not user.is_active:
            return None

        if not _verify_password(password, user.password_hash):
            return None

        # Update last login
        self.update_last_login(user.id)

        return user

    def update_last_login(self, user_id: int) -> None:
        """Update user's last login timestamp."""
        session, should_close = self._get_session()
        try:
            user = session.query(UserORM).filter(UserORM.id == user_id).first()
            if user:
                user.last_login = datetime.utcnow()
                if should_close:
                    session.commit()
        finally:
            if should_close:
                session.close()

    def update_password(self, user_id: int, new_password: str) -> bool:
        """
        Update a user's password.

        Args:
            user_id: User ID
            new_password: New plaintext password (will be hashed)

        Returns:
            True if updated, False if user not found
        """
        session, should_close = self._get_session()
        try:
            user = session.query(UserORM).filter(UserORM.id == user_id).first()
            if not user:
                return False

            hash_value, salt = _hash_password(new_password)
            user.password_hash = f"{salt}${hash_value}"

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

    def email_exists(self, email: str) -> bool:
        """Check if email is already registered."""
        session, should_close = self._get_session()
        try:
            count = session.query(func.count(UserORM.id)).filter(
                UserORM.email == email.lower()
            ).scalar()
            return count > 0
        finally:
            if should_close:
                session.close()