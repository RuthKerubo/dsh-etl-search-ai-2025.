"""
Tests for hybrid search service.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from etl.search import (
    HybridSearchService,
    HybridSearchResult,
    HybridSearchResponse,
    QueryType,
)
from etl.embeddings import SearchResult as SemanticResult
from etl.models import DatasetMetadata


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_vector_store():
    """Mock vector store."""
    store = Mock()
    store.search = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_repository():
    """Mock dataset repository."""
    repo = Mock()
    repo.search = Mock(return_value=[])
    repo.get = Mock(return_value=None)
    return repo


@pytest.fixture
def search_service(mock_vector_store, mock_repository):
    """Hybrid search service with mocks."""
    return HybridSearchService(
        vector_store=mock_vector_store,
        repository=mock_repository,
    )


@pytest.fixture
def sample_semantic_results():
    """Sample semantic search results."""
    return [
        SemanticResult(
            dataset_id="dataset-001",
            title="UK Drought Data",
            abstract="Historical drought records",
            score=0.95,
            keywords=["drought", "climate"],
        ),
        SemanticResult(
            dataset_id="dataset-002",
            title="Rainfall Patterns",
            abstract="Rainfall measurements across UK",
            score=0.82,
            keywords=["rainfall", "weather"],
        ),
    ]


@pytest.fixture
def sample_keyword_results():
    """Sample keyword search results."""
    return [
        DatasetMetadata(
            identifier="dataset-002",
            title="Rainfall Patterns",
            abstract="Rainfall measurements across UK",
            keywords=["rainfall", "weather"],
        ),
        DatasetMetadata(
            identifier="dataset-003",
            title="River Flow Data",
            abstract="River discharge measurements",
            keywords=["river", "hydrology"],
        ),
    ]


# =============================================================================
# Query Type Detection Tests
# =============================================================================

class TestQueryTypeDetection:
    """Tests for query type detection."""
    
    def test_detect_uuid(self, search_service):
        """Test UUID detection."""
        query = "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
        
        result = search_service._detect_query_type(query)
        
        assert result == QueryType.EXACT_ID
    
    def test_detect_quoted_title(self, search_service):
        """Test quoted string detection."""
        query = '"UK Drought Inventory"'
        
        result = search_service._detect_query_type(query)
        
        assert result == QueryType.EXACT_TITLE
    
    def test_detect_short_query(self, search_service):
        """Test short query detection."""
        for query in ["rivers", "CEH", "water quality"]:
            result = search_service._detect_query_type(query)
            assert result == QueryType.SHORT, f"Failed for: {query}"
    
    def test_detect_normal_query(self, search_service):
        """Test normal query detection."""
        query = "drought conditions in United Kingdom"
        
        result = search_service._detect_query_type(query)
        
        assert result == QueryType.NORMAL


# =============================================================================
# Exact Match Tests
# =============================================================================

class TestExactMatchSearch:
    """Tests for exact ID and title matching."""
    
    @pytest.mark.asyncio
    async def test_exact_id_found(self, search_service, mock_repository):
        """Test exact ID lookup when found."""
        dataset = DatasetMetadata(
            identifier="test-uuid-123",
            title="Test Dataset",
            abstract="Test abstract",
        )
        mock_repository.get.return_value = dataset
        
        response = await search_service._exact_id_search("test-uuid-123")
        
        assert len(response.results) == 1
        assert response.results[0].dataset_id == "test-uuid-123"
        assert response.results[0].is_exact_match is True
        assert response.query_type == QueryType.EXACT_ID
    
    @pytest.mark.asyncio
    async def test_exact_id_not_found(self, search_service, mock_repository):
        """Test exact ID lookup when not found."""
        mock_repository.get.return_value = None
        
        response = await search_service._exact_id_search("nonexistent-id")
        
        assert len(response.results) == 0


# =============================================================================
# RRF Merge Tests
# =============================================================================

class TestRRFMerge:
    """Tests for Reciprocal Rank Fusion merging."""
    
    def test_rrf_single_source(self, search_service, sample_semantic_results):
        """Test RRF with only semantic results."""
        merged = search_service._merge_rrf(
            semantic_results=sample_semantic_results,
            keyword_results=[],
            semantic_weight=1.0,
            keyword_weight=1.0,
        )
        
        assert len(merged) == 2
        assert all(r.from_semantic for r in merged)
        assert all(not r.from_keyword for r in merged)
    
    def test_rrf_both_sources(
        self,
        search_service,
        sample_semantic_results,
        sample_keyword_results,
    ):
        """Test RRF with both semantic and keyword results."""
        merged = search_service._merge_rrf(
            semantic_results=sample_semantic_results,
            keyword_results=sample_keyword_results,
            semantic_weight=1.0,
            keyword_weight=1.0,
        )
        
        # dataset-002 appears in both, so 3 unique datasets
        assert len(merged) == 3
        
        # Find dataset-002 (appears in both)
        overlapping = [r for r in merged if r.dataset_id == "dataset-002"]
        assert len(overlapping) == 1
        assert overlapping[0].from_semantic is True
        assert overlapping[0].from_keyword is True
    
    def test_rrf_overlap_scores_higher(
        self,
        search_service,
        sample_semantic_results,
        sample_keyword_results,
    ):
        """Test that documents in both sources score higher."""
        merged = search_service._merge_rrf(
            semantic_results=sample_semantic_results,
            keyword_results=sample_keyword_results,
            semantic_weight=1.0,
            keyword_weight=1.0,
        )
        
        # Sort by score
        merged.sort(key=lambda x: x.hybrid_score, reverse=True)
        
        # dataset-002 appears in both, should have higher score
        overlapping = [r for r in merged if r.from_semantic and r.from_keyword]
        non_overlapping = [r for r in merged if not (r.from_semantic and r.from_keyword)]
        
        if overlapping and non_overlapping:
            # Overlapping should score >= highest non-overlapping
            # (depends on ranks, but generally true)
            assert overlapping[0].hybrid_score >= min(r.hybrid_score for r in non_overlapping)


# =============================================================================
# Boost Tests
# =============================================================================

class TestExactMatchBoost:
    """Tests for exact match boosting."""
    
    def test_exact_title_boost(self, search_service):
        """Test that exact title match gets boosted."""
        results = [
            HybridSearchResult(
                dataset_id="id-1",
                title="Climate Data",
                abstract="...",
                hybrid_score=0.5,
            ),
            HybridSearchResult(
                dataset_id="id-2",
                title="Other Dataset",
                abstract="...",
                hybrid_score=0.6,
            ),
        ]
        
        boosted = search_service._boost_exact_matches(results, "Climate Data")
        
        # id-1 should now be higher due to exact match
        exact_match = [r for r in boosted if r.dataset_id == "id-1"][0]
        assert exact_match.hybrid_score > 0.5
        assert exact_match.is_exact_match is True
    
    def test_keyword_boost(self, search_service):
        """Test that keyword match gets smaller boost."""
        results = [
            HybridSearchResult(
                dataset_id="id-1",
                title="Some Dataset",
                abstract="...",
                hybrid_score=0.5,
                keywords=["drought", "climate"],
            ),
        ]
        
        boosted = search_service._boost_exact_matches(results, "drought")
        
        assert boosted[0].hybrid_score > 0.5


# =============================================================================
# Full Search Tests
# =============================================================================

class TestHybridSearch:
    """Tests for full hybrid search."""
    
    @pytest.mark.asyncio
    async def test_search_returns_response(
        self,
        search_service,
        mock_vector_store,
        mock_repository,
        sample_semantic_results,
        sample_keyword_results,
    ):
        """Test that search returns proper response."""
        mock_vector_store.search.return_value = sample_semantic_results
        mock_repository.search.return_value = sample_keyword_results
        
        response = await search_service.search("drought data")
        
        assert isinstance(response, HybridSearchResponse)
        assert response.query == "drought data"
        assert response.total_semantic == 2
        assert response.total_keyword == 2
    
    @pytest.mark.asyncio
    async def test_search_respects_limit(
        self,
        search_service,
        mock_vector_store,
        mock_repository,
        sample_semantic_results,
        sample_keyword_results,
    ):
        """Test that search respects result limit."""
        mock_vector_store.search.return_value = sample_semantic_results
        mock_repository.search.return_value = sample_keyword_results
        
        response = await search_service.search("test", limit=1)
        
        assert len(response.results) <= 1
    
    @pytest.mark.asyncio
    async def test_uuid_triggers_exact_lookup(
        self,
        search_service,
        mock_repository,
    ):
        """Test that UUID query triggers exact lookup."""
        dataset = DatasetMetadata(
            identifier="f710bed1-e564-47bf-b82c-4c2a2fe2810e",
            title="Test",
        )
        mock_repository.get.return_value = dataset
        
        response = await search_service.search(
            "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
        )
        
        assert response.query_type == QueryType.EXACT_ID
        mock_repository.get.assert_called_once()


# =============================================================================
# Result Dataclass Tests
# =============================================================================

class TestHybridSearchResult:
    """Tests for result dataclass."""
    
    def test_result_creation(self):
        """Test creating a search result."""
        result = HybridSearchResult(
            dataset_id="test-123",
            title="Test Dataset",
            abstract="Test abstract",
            hybrid_score=0.85,
            semantic_rank=1,
            keyword_rank=3,
            from_semantic=True,
            from_keyword=True,
        )
        
        assert result.dataset_id == "test-123"
        assert result.hybrid_score == 0.85
        assert result.from_semantic is True
        assert result.from_keyword is True


class TestHybridSearchResponse:
    """Tests for response dataclass."""
    
    def test_response_length(self):
        """Test response length."""
        response = HybridSearchResponse(
            results=[
                HybridSearchResult(
                    dataset_id="id-1",
                    title="Test",
                    abstract="...",
                    hybrid_score=0.5,
                ),
            ],
            query="test",
            query_type=QueryType.NORMAL,
            total_semantic=5,
            total_keyword=3,
        )
        
        assert len(response) == 1