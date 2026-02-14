"""
Hybrid Search Service.

Combines semantic (vector) and keyword (SQL) search using
Reciprocal Rank Fusion (RRF) for result merging.

Why hybrid?
- Semantic: Great for concepts ("water scarcity" finds "drought")
- Keyword: Great for exact matches (IDs, titles, organisations)
- Hybrid: Best of both worlds

Design:
- Auto-detects query type (short → more keyword weight)
- Uses RRF for merging (no score normalization needed)
- Exact matches get boosted to top
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re

from etl.embeddings import VectorStore, SearchResult as SemanticResult
from etl.repository import DatasetRepository
from etl.models.dataset import DatasetMetadata


class QueryType(str, Enum):
    """Detected query type."""
    EXACT_ID = "exact_id"           # UUID pattern
    EXACT_TITLE = "exact_title"     # Quoted string
    SHORT = "short"                 # 1-2 words
    NORMAL = "normal"               # Regular query


@dataclass
class HybridSearchResult:
    """A single search result with hybrid scoring."""
    dataset_id: str
    title: str
    abstract: str

    # Scores
    hybrid_score: float          # Combined RRF score
    semantic_rank: Optional[int] = None  # Rank in semantic results (None if not found)
    keyword_rank: Optional[int] = None   # Rank in keyword results (None if not found)

    # Source flags
    from_semantic: bool = False
    from_keyword: bool = False
    is_exact_match: bool = False

    # Metadata
    keywords: list[str] = field(default_factory=list)
    organisation: Optional[str] = None


@dataclass
class HybridSearchResponse:
    """Response from hybrid search."""
    results: list[HybridSearchResult]
    query: str
    query_type: QueryType
    total_semantic: int
    total_keyword: int

    def __len__(self) -> int:
        return len(self.results)


class HybridSearchService:
    """
    Hybrid search combining semantic and keyword search.

    Features:
    - Auto-detects query type
    - RRF (Reciprocal Rank Fusion) for merging
    - Exact match boosting
    - No user configuration needed

    Example:
        service = HybridSearchService(
            vector_store=store,
            repository=repository,
        )

        # Just search - it figures out the best approach
        response = await service.search("drought UK")

        # Or search for exact ID
        response = await service.search("f710bed1-e564-47bf-b82c-4c2a2fe2810e")
    """

    # RRF constant (standard value from literature)
    RRF_K = 60

    # UUID pattern for exact ID matching
    UUID_PATTERN = re.compile(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        re.IGNORECASE
    )

    def __init__(
        self,
        vector_store: VectorStore,
        repository: DatasetRepository,
        semantic_weight: float = 1.0,
        keyword_weight: float = 1.0,
        exact_match_boost: float = 10.0,
    ):
        """
        Initialize hybrid search.

        Args:
            vector_store: Vector store for semantic search
            repository: Repository for keyword search
            semantic_weight: Weight for semantic results in RRF
            keyword_weight: Weight for keyword results in RRF
            exact_match_boost: Score boost for exact ID/title matches
        """
        self.vector_store = vector_store
        self.repository = repository
        self.semantic_weight = semantic_weight
        self.keyword_weight = keyword_weight
        self.exact_match_boost = exact_match_boost

    async def search(
        self,
        query: str,
        limit: int = 10,
        semantic_limit: int = 50,
        keyword_limit: int = 50,
    ) -> HybridSearchResponse:
        """
        Perform hybrid search.

        Args:
            query: Search query
            limit: Final results to return
            semantic_limit: Max results from semantic search
            keyword_limit: Max results from keyword search

        Returns:
            HybridSearchResponse with merged results
        """
        query = query.strip()
        query_type = self._detect_query_type(query)

        # Handle exact ID lookup
        if query_type == QueryType.EXACT_ID:
            return await self._exact_id_search(query)

        # Handle exact title lookup (quoted)
        if query_type == QueryType.EXACT_TITLE:
            clean_query = query.strip('"\'')
            return await self._exact_title_search(clean_query, limit)

        # Adjust weights for short queries (favor keyword)
        semantic_w = self.semantic_weight
        keyword_w = self.keyword_weight

        if query_type == QueryType.SHORT:
            keyword_w *= 1.5  # Boost keyword for short queries

        # Run both searches in parallel
        import asyncio
        semantic_task = self.vector_store.search(query, limit=semantic_limit)
        keyword_results = self.repository.search(query, limit=keyword_limit)

        semantic_results = await semantic_task

        # Merge using RRF
        merged = self._merge_rrf(
            semantic_results=semantic_results,
            keyword_results=keyword_results,
            semantic_weight=semantic_w,
            keyword_weight=keyword_w,
        )

        # Check for exact matches and boost them
        merged = self._boost_exact_matches(merged, query)

        # Sort by hybrid score and limit
        merged.sort(key=lambda x: x.hybrid_score, reverse=True)

        return HybridSearchResponse(
            results=merged[:limit],
            query=query,
            query_type=query_type,
            total_semantic=len(semantic_results),
            total_keyword=len(keyword_results),
        )

    def _detect_query_type(self, query: str) -> QueryType:
        """Detect the type of query for optimal handling."""
        # Check for UUID
        if self.UUID_PATTERN.match(query):
            return QueryType.EXACT_ID

        # Check for quoted exact match
        if (query.startswith('"') and query.endswith('"')) or \
           (query.startswith("'") and query.endswith("'")):
            return QueryType.EXACT_TITLE

        # Check for short query (1-2 words)
        words = query.split()
        if len(words) <= 2:
            return QueryType.SHORT

        return QueryType.NORMAL

    async def _exact_id_search(self, dataset_id: str) -> HybridSearchResponse:
        """Handle exact ID lookup."""
        dataset = self.repository.get(dataset_id)

        if dataset:
            result = HybridSearchResult(
                dataset_id=dataset.identifier,
                title=dataset.title or "",
                abstract=dataset.abstract or "",
                hybrid_score=1.0,
                is_exact_match=True,
                from_keyword=True,
                keywords=dataset.keywords,
            )
            results = [result]
        else:
            results = []

        return HybridSearchResponse(
            results=results,
            query=dataset_id,
            query_type=QueryType.EXACT_ID,
            total_semantic=0,
            total_keyword=1 if results else 0,
        )

    async def _exact_title_search(
        self,
        title: str,
        limit: int,
    ) -> HybridSearchResponse:
        """Handle exact title search."""
        # Use keyword search with exact query
        results = self.repository.search(title, limit=limit)

        hybrid_results = []
        for i, dataset in enumerate(results):
            is_exact = dataset.title and title.lower() in dataset.title.lower()

            hybrid_results.append(HybridSearchResult(
                dataset_id=dataset.identifier,
                title=dataset.title or "",
                abstract=dataset.abstract or "",
                hybrid_score=1.0 if is_exact else 0.5,
                keyword_rank=i + 1,
                is_exact_match=is_exact,
                from_keyword=True,
                keywords=dataset.keywords,
            ))

        return HybridSearchResponse(
            results=hybrid_results,
            query=title,
            query_type=QueryType.EXACT_TITLE,
            total_semantic=0,
            total_keyword=len(results),
        )

    def _merge_rrf(
        self,
        semantic_results: list[SemanticResult],
        keyword_results: list[DatasetMetadata],
        semantic_weight: float,
        keyword_weight: float,
    ) -> list[HybridSearchResult]:
        """
        Merge results using Reciprocal Rank Fusion.

        RRF score = Σ (weight / (k + rank))

        This is rank-based, so no score normalization needed.
        """
        # Build score map
        scores: dict[str, HybridSearchResult] = {}

        # Process semantic results
        for rank, result in enumerate(semantic_results, start=1):
            rrf_score = semantic_weight / (self.RRF_K + rank)

            if result.dataset_id not in scores:
                scores[result.dataset_id] = HybridSearchResult(
                    dataset_id=result.dataset_id,
                    title=result.title,
                    abstract=result.abstract,
                    hybrid_score=0,
                    keywords=result.keywords,
                )

            scores[result.dataset_id].hybrid_score += rrf_score
            scores[result.dataset_id].semantic_rank = rank
            scores[result.dataset_id].from_semantic = True

        # Process keyword results
        for rank, dataset in enumerate(keyword_results, start=1):
            rrf_score = keyword_weight / (self.RRF_K + rank)

            if dataset.identifier not in scores:
                scores[dataset.identifier] = HybridSearchResult(
                    dataset_id=dataset.identifier,
                    title=dataset.title or "",
                    abstract=dataset.abstract or "",
                    hybrid_score=0,
                    keywords=dataset.keywords,
                )

            scores[dataset.identifier].hybrid_score += rrf_score
            scores[dataset.identifier].keyword_rank = rank
            scores[dataset.identifier].from_keyword = True

            # Extract organisation from responsible parties
            if dataset.responsible_parties:
                for party in dataset.responsible_parties:
                    if party.organisation:
                        scores[dataset.identifier].organisation = party.organisation
                        break

        return list(scores.values())

    def _boost_exact_matches(
        self,
        results: list[HybridSearchResult],
        query: str,
    ) -> list[HybridSearchResult]:
        """Boost results that exactly match query in title or ID."""
        query_lower = query.lower()

        for result in results:
            # Exact title match
            if result.title and query_lower == result.title.lower():
                result.hybrid_score += self.exact_match_boost
                result.is_exact_match = True

            # Title contains exact query
            elif result.title and query_lower in result.title.lower():
                result.hybrid_score += self.exact_match_boost * 0.5

            # Exact keyword match
            if any(query_lower == kw.lower() for kw in result.keywords):
                result.hybrid_score += self.exact_match_boost * 0.3

        return results

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    async def search_semantic_only(
        self,
        query: str,
        limit: int = 10,
    ) -> list[HybridSearchResult]:
        """Search using only semantic/vector search."""
        results = await self.vector_store.search(query, limit=limit)

        return [
            HybridSearchResult(
                dataset_id=r.dataset_id,
                title=r.title,
                abstract=r.abstract,
                hybrid_score=r.score,
                semantic_rank=i + 1,
                from_semantic=True,
                keywords=r.keywords,
            )
            for i, r in enumerate(results)
        ]

    def search_keyword_only(
        self,
        query: str,
        limit: int = 10,
    ) -> list[HybridSearchResult]:
        """Search using only keyword/SQL search."""
        results = self.repository.search(query, limit=limit)

        return [
            HybridSearchResult(
                dataset_id=d.identifier,
                title=d.title or "",
                abstract=d.abstract or "",
                hybrid_score=1.0 / (i + 1),  # Simple rank-based score
                keyword_rank=i + 1,
                from_keyword=True,
                keywords=d.keywords,
            )
            for i, d in enumerate(results)
        ]

    async def search_by_organisation(
        self,
        organisation: str,
        query: Optional[str] = None,
        limit: int = 10,
    ) -> list[HybridSearchResult]:
        """
        Search for datasets from a specific organisation.

        Optionally combine with a semantic query.
        """
        # This would need a repository method to filter by organisation
        # For now, use keyword search on organisation name
        org_results = self.repository.search(organisation, limit=limit * 2)

        if query:
            # Also run semantic search and merge
            semantic_results = await self.vector_store.search(query, limit=limit)

            # Filter semantic results to only those from this org
            org_ids = {d.identifier for d in org_results}
            filtered_semantic = [r for r in semantic_results if r.dataset_id in org_ids]

            return [
                HybridSearchResult(
                    dataset_id=r.dataset_id,
                    title=r.title,
                    abstract=r.abstract,
                    hybrid_score=r.score,
                    from_semantic=True,
                    keywords=r.keywords,
                )
                for r in filtered_semantic[:limit]
            ]

        return [
            HybridSearchResult(
                dataset_id=d.identifier,
                title=d.title or "",
                abstract=d.abstract or "",
                hybrid_score=1.0 / (i + 1),
                keyword_rank=i + 1,
                from_keyword=True,
                keywords=d.keywords,
            )
            for i, d in enumerate(org_results[:limit])
        ]


# =============================================================================
# Simple function interface
# =============================================================================

async def hybrid_search(
    query: str,
    vector_store: VectorStore,
    repository: DatasetRepository,
    limit: int = 10,
) -> list[HybridSearchResult]:
    """
    Simple function interface for hybrid search.

    Example:
        results = await hybrid_search("drought data UK", store, repo)
    """
    service = HybridSearchService(vector_store, repository)
    response = await service.search(query, limit=limit)
    return response.results