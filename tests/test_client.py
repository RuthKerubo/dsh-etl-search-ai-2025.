"""
Tests for CEH Catalogue Client.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import timedelta

from etl.client import (
    CEHCatalogueClient,
    BatchFetchResult,
    DatasetFetchResult,
    FetchFormat,
    ProgressUpdate,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client(tmp_path):
    """CEH client with temp cache."""
    return CEHCatalogueClient(
        cache_dir=tmp_path / "cache",
        concurrency=2,
        request_delay=0.1,
    )


# =============================================================================
# Client Initialization Tests
# =============================================================================

class TestCEHCatalogueClient:
    """Tests for CEH client initialization."""
    
    def test_client_creation(self, client):
        """Test client initializes correctly."""
        assert client is not None
        assert client._concurrency == 2
        assert client._request_delay == 0.1
    
    def test_client_with_defaults(self, tmp_path):
        """Test client with default settings."""
        client = CEHCatalogueClient(cache_dir=tmp_path / "cache")
        
        assert client._concurrency == 3
        assert client._request_delay == 0.3


# =============================================================================
# DatasetFetchResult Tests
# =============================================================================

class TestDatasetFetchResult:
    """Tests for fetch result dataclass."""
    
    def test_successful_result(self):
        """Test successful fetch result."""
        result = DatasetFetchResult(
            dataset_id="test-123",
            success=True,
            json_content='{"title": "Test"}',
        )
        
        assert result.success is True
        assert result.json_content is not None
        assert result.error is None
    
    def test_failed_result(self):
        """Test failed fetch result."""
        result = DatasetFetchResult(
            dataset_id="test-123",
            success=False,
            error="Connection timeout",
        )
        
        assert result.success is False
        assert result.error == "Connection timeout"


# =============================================================================
# BatchFetchResult Tests
# =============================================================================

class TestBatchFetchResult:
    """Tests for batch fetch result."""
    
    def test_empty_batch(self):
        """Test empty batch result."""
        result = BatchFetchResult()
        
        assert result.total == 0
        assert result.success_rate == 0.0
    
    def test_batch_with_results(self):
        """Test batch with mixed results."""
        result = BatchFetchResult()
        result.successful.append(DatasetFetchResult(
            dataset_id="id-1", success=True
        ))
        result.failed.append(DatasetFetchResult(
            dataset_id="id-2", success=False, error="Failed"
        ))
        
        assert result.total == 2
        assert result.success_rate == 0.5
    
    def test_summary(self):
        """Test summary generation."""
        result = BatchFetchResult()
        result.successful.append(DatasetFetchResult(
            dataset_id="id-1", success=True
        ))
        
        summary = result.summary()
        
        assert "1" in summary
        assert "succeeded" in summary


# =============================================================================
# FetchFormat Tests
# =============================================================================

class TestFetchFormat:
    """Tests for fetch format enum."""
    
    def test_format_values(self):
        """Test format enum values."""
        assert FetchFormat.JSON.value == "json"
        assert FetchFormat.XML.value == "gemini"


# =============================================================================
# ProgressUpdate Tests
# =============================================================================

class TestProgressUpdate:
    """Tests for progress updates."""
    
    def test_progress_percentage(self):
        """Test progress percentage calculation."""
        update = ProgressUpdate(
            dataset_id="test-123",
            current=50,
            total=100,
            status="fetching",
        )
        
        assert update.progress_pct == 50.0
    
    def test_progress_zero_total(self):
        """Test progress with zero total."""
        update = ProgressUpdate(
            dataset_id="test-123",
            current=0,
            total=0,
            status="fetching",
        )
        
        assert update.progress_pct == 0.0