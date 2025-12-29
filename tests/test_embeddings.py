"""
Tests for embedding services and vector store.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from etl.embeddings import (
    EmbeddingService,
    CohereEmbeddingService,
    VectorStore,
    SearchResult,
    IndexingResult,
)
from etl.models import DatasetMetadata


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_embedding_service():
    """Mock embedding service for testing without API calls."""
    service = Mock(spec=EmbeddingService)
    service.model_name = "test-model"
    service.dimensions = 1024
    
    # Return fake embeddings (list of floats)
    fake_embedding = [0.1] * 1024
    
    service.embed_query = AsyncMock(return_value=fake_embedding)
    service.embed_batch = AsyncMock(return_value=[fake_embedding])
    
    return service


@pytest.fixture
def vector_store(tmp_path, mock_embedding_service):
    """Vector store with mock embeddings and temp storage."""
    return VectorStore(
        embedding_service=mock_embedding_service,
        persist_path=tmp_path / "chroma",
    )


@pytest.fixture
def sample_datasets():
    """Sample datasets for testing."""
    return [
        DatasetMetadata(
            identifier="dataset-001",
            title="UK Climate Data",
            abstract="Temperature and rainfall measurements across the UK.",
            keywords=["climate", "temperature", "rainfall"],
        ),
        DatasetMetadata(
            identifier="dataset-002",
            title="River Water Quality",
            abstract="Water quality measurements from major UK rivers.",
            keywords=["water", "quality", "rivers"],
        ),
        DatasetMetadata(
            identifier="dataset-003",
            title="Land Cover Map",
            abstract="Satellite-derived land cover classification for Britain.",
            keywords=["land", "cover", "satellite"],
        ),
    ]


# =============================================================================
# EmbeddingService Base Tests
# =============================================================================

class TestEmbeddingServiceInterface:
    """Tests for the embedding service interface."""
    
    def test_mock_service_has_required_properties(self, mock_embedding_service):
        """Test that mock implements the interface."""
        assert mock_embedding_service.model_name == "test-model"
        assert mock_embedding_service.dimensions == 1024
    
    @pytest.mark.asyncio
    async def test_embed_query_returns_list(self, mock_embedding_service):
        """Test embed_query returns a list of floats."""
        result = await mock_embedding_service.embed_query("test query")
        
        assert isinstance(result, list)
        assert len(result) == 1024
        assert all(isinstance(x, float) for x in result)
    
    @pytest.mark.asyncio
    async def test_embed_batch_returns_list_of_lists(self, mock_embedding_service):
        """Test embed_batch returns list of embeddings."""
        result = await mock_embedding_service.embed_batch(["text1", "text2"])
        
        assert isinstance(result, list)
        assert all(isinstance(emb, list) for emb in result)


# =============================================================================
# VectorStore Tests
# =============================================================================

class TestVectorStore:
    """Tests for ChromaDB vector store."""
    
    def test_store_creation(self, vector_store):
        """Test vector store initializes correctly."""
        assert vector_store is not None
        assert vector_store._collection is not None
    
    def test_get_stats_empty(self, vector_store):
        """Test stats on empty store."""
        stats = vector_store.get_stats()
        
        assert stats["total_documents"] == 0
        assert stats["collection_name"] == "datasets"
        assert "persist_path" in stats
    
    @pytest.mark.asyncio
    async def test_add_single_dataset(self, vector_store, sample_datasets):
        """Test adding a single dataset."""
        dataset = sample_datasets[0]
        
        success = await vector_store.add_single(dataset)
        
        assert success is True
        assert vector_store.is_indexed(dataset.identifier)
    
    @pytest.mark.asyncio
    async def test_add_multiple_datasets(self, vector_store, sample_datasets, mock_embedding_service):
        """Test adding multiple datasets."""
        # Update mock to return correct number of embeddings
        fake_embedding = [0.1] * 1024
        mock_embedding_service.embed_batch = AsyncMock(
            return_value=[fake_embedding] * len(sample_datasets)
        )
        
        result = await vector_store.add_datasets(sample_datasets)
        
        assert result.total == 3
        assert len(result.successful) == 3
        assert len(result.failed) == 0
        assert result.success_rate == 1.0
    
    @pytest.mark.asyncio
    async def test_skip_existing_datasets(self, vector_store, sample_datasets, mock_embedding_service):
        """Test that existing datasets are skipped."""
        fake_embedding = [0.1] * 1024
        mock_embedding_service.embed_batch = AsyncMock(
            return_value=[fake_embedding] * len(sample_datasets)
        )
        
        # Add first time
        await vector_store.add_datasets(sample_datasets)
        
        # Add again with skip_existing=True
        result = await vector_store.add_datasets(sample_datasets, skip_existing=True)
        
        assert result.total == 0  # All skipped
    
    @pytest.mark.asyncio
    async def test_search_returns_results(self, vector_store, sample_datasets, mock_embedding_service):
        """Test semantic search."""
        fake_embedding = [0.1] * 1024
        mock_embedding_service.embed_batch = AsyncMock(
            return_value=[fake_embedding] * len(sample_datasets)
        )
        
        # Index datasets
        await vector_store.add_datasets(sample_datasets)
        
        # Search
        results = await vector_store.search("climate data", limit=5)
        
        assert isinstance(results, list)
        # ChromaDB should return results
        assert len(results) > 0
    
    @pytest.mark.asyncio
    async def test_search_result_structure(self, vector_store, sample_datasets, mock_embedding_service):
        """Test SearchResult has correct fields."""
        fake_embedding = [0.1] * 1024
        mock_embedding_service.embed_batch = AsyncMock(
            return_value=[fake_embedding] * len(sample_datasets)
        )
        
        await vector_store.add_datasets(sample_datasets)
        results = await vector_store.search("test", limit=1)
        
        if results:
            result = results[0]
            assert hasattr(result, "dataset_id")
            assert hasattr(result, "title")
            assert hasattr(result, "abstract")
            assert hasattr(result, "score")
            assert hasattr(result, "keywords")
    
    def test_get_indexed_ids(self, vector_store):
        """Test getting indexed IDs."""
        ids = vector_store.get_indexed_ids()
        assert isinstance(ids, list)
    
    def test_is_indexed_false_for_missing(self, vector_store):
        """Test is_indexed returns False for non-existent."""
        assert vector_store.is_indexed("nonexistent-id") is False
    
    @pytest.mark.asyncio
    async def test_delete_dataset(self, vector_store, sample_datasets):
        """Test deleting a dataset."""
        dataset = sample_datasets[0]
        await vector_store.add_single(dataset)
        
        assert vector_store.is_indexed(dataset.identifier)
        
        success = vector_store.delete(dataset.identifier)
        
        assert success is True
        assert not vector_store.is_indexed(dataset.identifier)
    
    @pytest.mark.asyncio
    async def test_clear_store(self, vector_store, sample_datasets, mock_embedding_service):
        """Test clearing all data."""
        fake_embedding = [0.1] * 1024
        mock_embedding_service.embed_batch = AsyncMock(
            return_value=[fake_embedding] * len(sample_datasets)
        )
        
        await vector_store.add_datasets(sample_datasets)
        assert vector_store.get_stats()["total_documents"] == 3
        
        count = vector_store.clear()
        
        assert count == 3
        assert vector_store.get_stats()["total_documents"] == 0


# =============================================================================
# IndexingResult Tests
# =============================================================================

class TestIndexingResult:
    """Tests for IndexingResult dataclass."""
    
    def test_empty_result(self):
        """Test empty result."""
        result = IndexingResult()
        
        assert result.total == 0
        assert result.success_rate == 0.0
    
    def test_success_tracking(self):
        """Test tracking successes."""
        result = IndexingResult()
        result.successful.append("id-1")
        result.successful.append("id-2")
        
        assert result.total == 2
        assert result.success_rate == 1.0
    
    def test_failure_tracking(self):
        """Test tracking failures."""
        result = IndexingResult()
        result.successful.append("id-1")
        result.failed.append(("id-2", "Some error"))
        
        assert result.total == 2
        assert result.success_rate == 0.5
    
    def test_summary(self):
        """Test summary generation."""
        result = IndexingResult()
        result.successful.append("id-1")
        
        summary = result.summary()
        
        assert "1/1" in summary
        assert "100.0%" in summary


# =============================================================================
# SearchResult Tests
# =============================================================================

class TestSearchResult:
    """Tests for SearchResult dataclass."""
    
    def test_search_result_creation(self):
        """Test creating a search result."""
        result = SearchResult(
            dataset_id="test-123",
            title="Test Dataset",
            abstract="This is a test.",
            score=0.95,
            keywords=["test", "example"],
        )
        
        assert result.dataset_id == "test-123"
        assert result.score == 0.95
        assert len(result.keywords) == 2