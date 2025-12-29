"""
Tests for ETL Pipeline.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
from datetime import datetime

from etl.pipeline import (
    ETLPipeline,
    ResumableETLPipeline,
    PipelineConfig,
    PipelineResult,
    PipelineStage,
    ProcessedDataset,
    Checkpoint,
)


# =============================================================================
# PipelineConfig Tests
# =============================================================================

class TestPipelineConfig:
    """Tests for pipeline configuration."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = PipelineConfig()
        
        assert config.batch_size == 20
        assert config.stop_on_error is False
        assert config.store_raw_documents is True
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = PipelineConfig(
            batch_size=50,
            stop_on_error=True,
        )
        
        assert config.batch_size == 50
        assert config.stop_on_error is True


# =============================================================================
# ProcessedDataset Tests
# =============================================================================

class TestProcessedDataset:
    """Tests for processed dataset result."""
    
    def test_successful_processing(self):
        """Test successful dataset processing."""
        processed = ProcessedDataset(
            dataset_id="test-123",
            success=True,
            stage_completed=PipelineStage.STORE,
        )
        
        assert processed.success is True
        assert processed.stage_completed == PipelineStage.STORE
    
    def test_failed_processing(self):
        """Test failed dataset processing."""
        processed = ProcessedDataset(
            dataset_id="test-123",
            success=False,
            stage_completed=PipelineStage.PARSE,
            error_stage=PipelineStage.PARSE,
            error_message="Invalid JSON",
        )
        
        assert processed.success is False
        assert processed.error_stage == PipelineStage.PARSE
    
    def test_duration_calculation(self):
        """Test duration is calculated."""
        processed = ProcessedDataset(
            dataset_id="test-123",
            success=True,
            stage_completed=PipelineStage.STORE,
        )
        processed.completed_at = datetime.utcnow()
        
        assert processed.duration_ms >= 0


# =============================================================================
# PipelineResult Tests
# =============================================================================

class TestPipelineResult:
    """Tests for pipeline result."""
    
    def test_empty_result(self):
        """Test empty result."""
        result = PipelineResult()
        
        assert result.total == 0
        assert result.success_count == 0
        assert result.failure_count == 0
    
    def test_with_successes(self):
        """Test result with successes."""
        result = PipelineResult()
        result.successful.append(ProcessedDataset(
            dataset_id="id-1",
            success=True,
            stage_completed=PipelineStage.STORE,
        ))
        
        assert result.total == 1
        assert result.success_count == 1
        assert result.success_rate == 1.0
    
    def test_with_failures(self):
        """Test result with failures."""
        result = PipelineResult()
        result.failed.append(ProcessedDataset(
            dataset_id="id-1",
            success=False,
            stage_completed=PipelineStage.FETCH,
            error_stage=PipelineStage.FETCH,
        ))
        
        assert result.failure_count == 1
        assert result.success_rate == 0.0
    
    def test_failures_by_stage(self):
        """Test counting failures by stage."""
        result = PipelineResult()
        result.failed.append(ProcessedDataset(
            dataset_id="id-1",
            success=False,
            stage_completed=PipelineStage.FETCH,
            error_stage=PipelineStage.FETCH,
        ))
        result.failed.append(ProcessedDataset(
            dataset_id="id-2",
            success=False,
            stage_completed=PipelineStage.PARSE,
            error_stage=PipelineStage.PARSE,
        ))
        
        by_stage = result.failures_by_stage()
        
        assert by_stage["fetch"] == 1
        assert by_stage["parse"] == 1
    
    def test_summary(self):
        """Test summary generation."""
        result = PipelineResult()
        result.successful.append(ProcessedDataset(
            dataset_id="id-1",
            success=True,
            stage_completed=PipelineStage.STORE,
        ))
        
        summary = result.summary()
        
        assert "1" in summary
        assert "Successful" in summary
    
    def test_to_dict(self):
        """Test conversion to dict."""
        result = PipelineResult()
        
        data = result.to_dict()
        
        assert "total" in data
        assert "successful" in data
        assert "failed" in data


# =============================================================================
# Checkpoint Tests
# =============================================================================

class TestCheckpoint:
    """Tests for pipeline checkpoint."""
    
    def test_empty_checkpoint(self):
        """Test empty checkpoint."""
        checkpoint = Checkpoint()
        
        assert len(checkpoint.processed_ids) == 0
        assert len(checkpoint.failed_ids) == 0
    
    def test_remaining_ids(self):
        """Test calculating remaining IDs."""
        checkpoint = Checkpoint()
        checkpoint.processed_ids.add("id-1")
        checkpoint.processed_ids.add("id-2")
        
        all_ids = ["id-1", "id-2", "id-3", "id-4"]
        remaining = checkpoint.remaining(all_ids)
        
        assert remaining == ["id-3", "id-4"]
    
    def test_save_and_load(self, tmp_path):
        """Test checkpoint save and load."""
        path = tmp_path / "checkpoint.json"
        
        # Save
        checkpoint = Checkpoint()
        checkpoint.processed_ids.add("id-1")
        checkpoint.failed_ids.add("id-2")
        checkpoint.save(path)
        
        # Load
        loaded = Checkpoint.load(path)
        
        assert "id-1" in loaded.processed_ids
        assert "id-2" in loaded.failed_ids
    
    def test_load_nonexistent(self, tmp_path):
        """Test loading non-existent checkpoint."""
        path = tmp_path / "nonexistent.json"
        
        checkpoint = Checkpoint.load(path)
        
        assert len(checkpoint.processed_ids) == 0


# =============================================================================
# PipelineStage Tests
# =============================================================================

class TestPipelineStage:
    """Tests for pipeline stage enum."""
    
    def test_stage_values(self):
        """Test stage enum values."""
        assert PipelineStage.FETCH.value == "fetch"
        assert PipelineStage.PARSE.value == "parse"
        assert PipelineStage.STORE.value == "store"
        assert PipelineStage.COMPLETE.value == "complete"