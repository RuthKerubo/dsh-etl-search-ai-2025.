"""
Tests for repository layer.
"""

import pytest
from pathlib import Path

from etl.repository import (
    SessionFactory,
    DatabaseConfig,
    DatasetRepository,
    UserRepository,
    SearchHistoryRepository,
    UnitOfWork,
    BulkOperationResult,
)
from etl.models import DatasetMetadata
from etl.models.user import User, UserCreate, SearchHistoryEntry


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def db_path(tmp_path):
    """Temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def session_factory(db_path):
    """Session factory with fresh database."""
    config = DatabaseConfig(database_path=db_path)
    factory = SessionFactory(config)
    factory.init_db()
    return factory


@pytest.fixture
def dataset_repo(session_factory):
    """Standalone dataset repository."""
    return DatasetRepository(session_factory)


@pytest.fixture
def user_repo(session_factory):
    """Standalone user repository."""
    return UserRepository(session_factory)


@pytest.fixture
def search_repo(session_factory):
    """Standalone search history repository."""
    return SearchHistoryRepository(session_factory)


@pytest.fixture
def sample_dataset():
    """Sample dataset for testing."""
    return DatasetMetadata(
        identifier="test-dataset-123",
        title="UK Climate Data",
        abstract="Temperature and rainfall measurements across the UK.",
        keywords=["climate", "temperature", "rainfall", "UK"],
    )


@pytest.fixture
def sample_user_create():
    """Sample user creation data."""
    return UserCreate(
        email="test@example.com",
        password="securepassword123",
        display_name="Test User",
    )


# =============================================================================
# Session Factory Tests
# =============================================================================

class TestSessionFactory:
    """Tests for SessionFactory."""
    
    def test_creates_database_file(self, db_path):
        """Test that init_db creates the database file."""
        config = DatabaseConfig(database_path=db_path)
        factory = SessionFactory(config)
        factory.init_db()
        
        assert db_path.exists()
    
    def test_creates_parent_directories(self, tmp_path):
        """Test that nested directories are created."""
        nested_path = tmp_path / "nested" / "dir" / "test.db"
        config = DatabaseConfig(database_path=nested_path)
        factory = SessionFactory(config)
        factory.init_db()
        
        assert nested_path.exists()
    
    def test_session_context_manager(self, session_factory):
        """Test session context manager."""
        from sqlalchemy import text
        
        with session_factory.session() as session:
            assert session is not None
            # Session should be usable
            result = session.execute(text("SELECT 1")).scalar()
            assert result == 1


# =============================================================================
# Dataset Repository Tests
# =============================================================================

class TestDatasetRepository:
    """Tests for DatasetRepository."""
    
    def test_save_and_get(self, dataset_repo, sample_dataset):
        """Test saving and retrieving a dataset."""
        # Save
        identifier = dataset_repo.save(sample_dataset)
        assert identifier == sample_dataset.identifier
        
        # Retrieve
        retrieved = dataset_repo.get(sample_dataset.identifier)
        assert retrieved is not None
        assert retrieved.identifier == sample_dataset.identifier
        assert retrieved.title == sample_dataset.title
        assert retrieved.abstract == sample_dataset.abstract
    
    def test_get_nonexistent_returns_none(self, dataset_repo):
        """Test that getting nonexistent dataset returns None."""
        result = dataset_repo.get("nonexistent-id")
        assert result is None
    
    def test_exists(self, dataset_repo, sample_dataset):
        """Test exists check."""
        assert not dataset_repo.exists(sample_dataset.identifier)
        
        dataset_repo.save(sample_dataset)
        
        assert dataset_repo.exists(sample_dataset.identifier)
    
    def test_count(self, dataset_repo, sample_dataset):
        """Test counting datasets."""
        assert dataset_repo.count() == 0
        
        dataset_repo.save(sample_dataset)
        assert dataset_repo.count() == 1
        
        # Save another
        another = DatasetMetadata(
            identifier="another-dataset",
            title="Another Dataset",
        )
        dataset_repo.save(another)
        assert dataset_repo.count() == 2
    
    def test_delete(self, dataset_repo, sample_dataset):
        """Test deleting a dataset."""
        dataset_repo.save(sample_dataset)
        assert dataset_repo.exists(sample_dataset.identifier)
        
        result = dataset_repo.delete(sample_dataset.identifier)
        assert result is True
        assert not dataset_repo.exists(sample_dataset.identifier)
    
    def test_delete_nonexistent_returns_false(self, dataset_repo):
        """Test deleting nonexistent dataset."""
        result = dataset_repo.delete("nonexistent")
        assert result is False
    
    def test_get_all(self, dataset_repo):
        """Test getting all datasets."""
        datasets = [
            DatasetMetadata(identifier=f"dataset-{i}", title=f"Dataset {i}")
            for i in range(3)
        ]
        
        for d in datasets:
            dataset_repo.save(d)
        
        all_datasets = dataset_repo.get_all()
        assert len(all_datasets) == 3
    
    def test_search_by_title(self, dataset_repo, sample_dataset):
        """Test searching by title."""
        dataset_repo.save(sample_dataset)
        
        results = dataset_repo.search("Climate")
        assert len(results) == 1
        assert results[0].identifier == sample_dataset.identifier
    
    def test_search_by_abstract(self, dataset_repo, sample_dataset):
        """Test searching by abstract."""
        dataset_repo.save(sample_dataset)
        
        results = dataset_repo.search("rainfall")
        assert len(results) == 1
    
    def test_search_case_insensitive(self, dataset_repo, sample_dataset):
        """Test that search is case insensitive."""
        dataset_repo.save(sample_dataset)
        
        results = dataset_repo.search("CLIMATE")
        assert len(results) == 1
    
    def test_search_no_results(self, dataset_repo, sample_dataset):
        """Test search with no matches."""
        dataset_repo.save(sample_dataset)
        
        results = dataset_repo.search("nonexistent term")
        assert len(results) == 0
    
    def test_update_existing(self, dataset_repo, sample_dataset):
        """Test updating an existing dataset."""
        dataset_repo.save(sample_dataset)
        
        # Update
        sample_dataset.title = "Updated Title"
        dataset_repo.save(sample_dataset)
        
        # Verify
        retrieved = dataset_repo.get(sample_dataset.identifier)
        assert retrieved.title == "Updated Title"
        assert dataset_repo.count() == 1  # Still only one record
    
    def test_save_many(self, dataset_repo):
        """Test bulk save operation."""
        datasets = [
            DatasetMetadata(identifier=f"bulk-{i}", title=f"Bulk Dataset {i}")
            for i in range(5)
        ]
        
        result = dataset_repo.save_many(datasets)
        
        assert result.success_count == 5
        assert result.failure_count == 0
        assert dataset_repo.count() == 5


# =============================================================================
# User Repository Tests
# =============================================================================

class TestUserRepository:
    """Tests for UserRepository."""
    
    def test_create_user(self, user_repo, sample_user_create):
        """Test creating a new user."""
        user = user_repo.create(sample_user_create)
        
        assert user.id is not None
        assert user.email == sample_user_create.email.lower()
        assert user.display_name == sample_user_create.display_name
        assert user.password_hash != sample_user_create.password  # Hashed
    
    def test_get_user_by_id(self, user_repo, sample_user_create):
        """Test getting user by ID."""
        created = user_repo.create(sample_user_create)
        
        retrieved = user_repo.get(created.id)
        assert retrieved is not None
        assert retrieved.email == created.email
    
    def test_get_user_by_email(self, user_repo, sample_user_create):
        """Test getting user by email."""
        user_repo.create(sample_user_create)
        
        retrieved = user_repo.get_by_email(sample_user_create.email)
        assert retrieved is not None
        assert retrieved.email == sample_user_create.email.lower()
    
    def test_email_case_insensitive(self, user_repo, sample_user_create):
        """Test that email lookup is case insensitive."""
        user_repo.create(sample_user_create)
        
        retrieved = user_repo.get_by_email("TEST@EXAMPLE.COM")
        assert retrieved is not None
    
    def test_authenticate_success(self, user_repo, sample_user_create):
        """Test successful authentication."""
        user_repo.create(sample_user_create)
        
        user = user_repo.authenticate(
            sample_user_create.email,
            sample_user_create.password,
        )
        
        assert user is not None
        assert user.email == sample_user_create.email.lower()
    
    def test_authenticate_wrong_password(self, user_repo, sample_user_create):
        """Test authentication with wrong password."""
        user_repo.create(sample_user_create)
        
        user = user_repo.authenticate(
            sample_user_create.email,
            "wrongpassword",
        )
        
        assert user is None
    
    def test_authenticate_nonexistent_user(self, user_repo):
        """Test authentication for nonexistent user."""
        user = user_repo.authenticate("nobody@example.com", "password")
        assert user is None
    
    def test_email_exists(self, user_repo, sample_user_create):
        """Test email existence check."""
        assert not user_repo.email_exists(sample_user_create.email)
        
        user_repo.create(sample_user_create)
        
        assert user_repo.email_exists(sample_user_create.email)
    
    def test_update_password(self, user_repo, sample_user_create):
        """Test password update."""
        user = user_repo.create(sample_user_create)
        
        new_password = "newpassword456"
        result = user_repo.update_password(user.id, new_password)
        assert result is True
        
        # Old password should fail
        assert user_repo.authenticate(user.email, sample_user_create.password) is None
        
        # New password should work
        assert user_repo.authenticate(user.email, new_password) is not None
    
    def test_delete_user(self, user_repo, sample_user_create):
        """Test deleting a user."""
        user = user_repo.create(sample_user_create)
        
        result = user_repo.delete(user.id)
        assert result is True
        assert user_repo.get(user.id) is None


# =============================================================================
# Search History Repository Tests
# =============================================================================

class TestSearchHistoryRepository:
    """Tests for SearchHistoryRepository."""
    
    def test_record_search(self, search_repo):
        """Test recording a search."""
        entry = search_repo.record_search(
            query_text="climate data",
            result_count=42,
            duration_ms=150,
        )
        
        assert entry.id is not None
        assert entry.query_text == "climate data"
        assert entry.result_count == 42
    
    def test_get_user_history(self, search_repo, user_repo, sample_user_create):
        """Test getting user's search history."""
        user = user_repo.create(sample_user_create)
        
        # Record some searches
        search_repo.record_search("query 1", 10, user_id=user.id)
        search_repo.record_search("query 2", 20, user_id=user.id)
        search_repo.record_search("query 3", 30, user_id=user.id)
        
        history = search_repo.get_user_history(user.id)
        
        assert len(history) == 3
        # Most recent first
        assert history[0].query_text == "query 3"
    
    def test_get_popular_queries(self, search_repo):
        """Test getting popular queries."""
        # Record same query multiple times
        for _ in range(5):
            search_repo.record_search("popular query", 10)
        for _ in range(3):
            search_repo.record_search("less popular", 5)
        search_repo.record_search("rare query", 2)
        
        popular = search_repo.get_popular_queries(days=1, limit=10)
        
        assert len(popular) >= 2
        # Most popular first
        assert popular[0][0].lower() == "popular query"
        assert popular[0][1] == 5
    
    def test_clear_user_history(self, search_repo, user_repo, sample_user_create):
        """Test clearing user's history."""
        user = user_repo.create(sample_user_create)
        
        search_repo.record_search("query", 10, user_id=user.id)
        search_repo.record_search("query", 10, user_id=user.id)
        
        count = search_repo.clear_user_history(user.id)
        assert count == 2
        
        history = search_repo.get_user_history(user.id)
        assert len(history) == 0


# =============================================================================
# Unit of Work Tests
# =============================================================================

class TestUnitOfWork:
    """Tests for UnitOfWork pattern."""
    
    def test_uow_commits_all_changes(self, session_factory):
        """Test that UoW commits all repository changes."""
        with UnitOfWork(session_factory) as uow:
            # Create user
            user = uow.users.create(UserCreate(
                email="uow@example.com",
                password="password",
            ))
            
            # Create dataset
            uow.datasets.save(DatasetMetadata(
                identifier="uow-dataset",
                title="UoW Test Dataset",
            ))
            
            # Record search
            uow.search_history.record_search("test query", 5, user_id=user.id)
            
            uow.commit()
        
        # Verify with standalone repos
        user_repo = UserRepository(session_factory)
        dataset_repo = DatasetRepository(session_factory)
        search_repo = SearchHistoryRepository(session_factory)
        
        assert user_repo.count() == 1
        assert dataset_repo.count() == 1
        assert search_repo.count() == 1
    
    def test_uow_rollback_on_exception(self, session_factory):
        """Test that UoW rolls back on exception."""
        try:
            with UnitOfWork(session_factory) as uow:
                uow.datasets.save(DatasetMetadata(
                    identifier="rollback-test",
                    title="Should be rolled back",
                ))
                raise ValueError("Simulated error")
        except ValueError:
            pass
        
        # Verify nothing was saved
        repo = DatasetRepository(session_factory)
        assert repo.count() == 0
    
    def test_uow_rollback_without_commit(self, session_factory):
        """Test that changes without commit are not persisted."""
        with UnitOfWork(session_factory) as uow:
            uow.datasets.save(DatasetMetadata(
                identifier="no-commit-test",
                title="Should not persist",
            ))
            # No commit() called
        
        # Verify nothing was saved
        repo = DatasetRepository(session_factory)
        assert repo.count() == 0
    
    def test_uow_lazy_repository_creation(self, session_factory):
        """Test that repositories are created lazily."""
        with UnitOfWork(session_factory) as uow:
            # Initially no repos created
            assert uow._datasets is None
            assert uow._users is None
            assert uow._search_history is None
            
            # Access creates them
            _ = uow.datasets
            assert uow._datasets is not None
            assert uow._users is None  # Still not created
    
    def test_uow_repos_share_session(self, session_factory):
        """Test that all repos in UoW share the same session."""
        with UnitOfWork(session_factory) as uow:
            datasets_session = uow.datasets._managed_session
            users_session = uow.users._managed_session
            history_session = uow.search_history._managed_session
            
            assert datasets_session is users_session
            assert users_session is history_session