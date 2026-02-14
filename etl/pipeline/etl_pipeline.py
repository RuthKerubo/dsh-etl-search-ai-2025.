"""
ETL Pipeline Orchestrator.

Wires together fetch → parse → store into a cohesive pipeline.
Handles batching, progress reporting, and error recovery.

Design decisions:
- Lightweight class (holds config, no deep inheritance)
- Batch commits every N datasets (safety + performance)
- Structured result object for reporting
- Embeddings are a separate pipeline (different failure modes)

Usage:
    pipeline = ETLPipeline(
        client=CEHCatalogueClient(cache_dir="./cache"),
        parser=CEHJSONParser(),
        session_factory=session_factory,
    )

    result = await pipeline.run(dataset_ids)
    print(result.summary())
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
import json
import traceback

from etl.client import CEHCatalogueClient, DatasetFetchResult, FetchFormat
from etl.parsers import MetadataParser, ParserRegistry, get_default_registry
from etl.repository import SessionFactory, UnitOfWork, DatasetRepository
from etl.models.dataset import DatasetMetadata


class PipelineStage(str, Enum):
    """Stages of the ETL pipeline."""
    FETCH = "fetch"
    PARSE = "parse"
    STORE = "store"
    COMPLETE = "complete"


@dataclass
class ProcessedDataset:
    """Result of processing a single dataset."""
    dataset_id: str
    success: bool
    stage_completed: PipelineStage

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Data (if successful)
    metadata: Optional[DatasetMetadata] = None
    from_cache: bool = False

    # Error (if failed)
    error_stage: Optional[PipelineStage] = None
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return 0


@dataclass
class PipelineResult:
    """
    Result of running the ETL pipeline.

    Provides structured access to successes, failures, and statistics.
    """
    successful: list[ProcessedDataset] = field(default_factory=list)
    failed: list[ProcessedDataset] = field(default_factory=list)

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    # Batch tracking
    batches_committed: int = 0

    @property
    def total(self) -> int:
        return len(self.successful) + len(self.failed)

    @property
    def success_count(self) -> int:
        return len(self.successful)

    @property
    def failure_count(self) -> int:
        return len(self.failed)

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total if self.total > 0 else 0.0

    @property
    def duration(self) -> timedelta:
        end = self.completed_at or datetime.utcnow()
        return end - self.started_at

    @property
    def cache_hit_rate(self) -> float:
        cached = sum(1 for r in self.successful if r.from_cache)
        return cached / self.success_count if self.success_count > 0 else 0.0

    @property
    def avg_duration_ms(self) -> float:
        if not self.successful:
            return 0
        total = sum(r.duration_ms for r in self.successful)
        return total / len(self.successful)

    def failures_by_stage(self) -> dict[str, int]:
        """Count failures by stage."""
        counts: dict[str, int] = {}
        for f in self.failed:
            stage = f.error_stage.value if f.error_stage else "unknown"
            counts[stage] = counts.get(stage, 0) + 1
        return counts

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"ETL Pipeline Complete",
            f"━━━━━━━━━━━━━━━━━━━━━",
            f"Total:      {self.total} datasets",
            f"Successful: {self.success_count} ({self.success_rate:.1%})",
            f"Failed:     {self.failure_count}",
            f"Duration:   {self.duration.total_seconds():.1f}s",
            f"Cache hits: {self.cache_hit_rate:.1%}",
            f"Batches:    {self.batches_committed}",
        ]

        if self.failed:
            lines.append(f"\nFailures by stage:")
            for stage, count in self.failures_by_stage().items():
                lines.append(f"  {stage}: {count}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total": self.total,
            "successful": self.success_count,
            "failed": self.failure_count,
            "success_rate": self.success_rate,
            "duration_seconds": self.duration.total_seconds(),
            "cache_hit_rate": self.cache_hit_rate,
            "batches_committed": self.batches_committed,
            "failures_by_stage": self.failures_by_stage(),
            "failed_ids": [f.dataset_id for f in self.failed],
        }


@dataclass
class PipelineConfig:
    """Configuration for the ETL pipeline."""

    # Batch settings
    batch_size: int = 20  # Commit every N datasets

    # Formats to fetch
    formats: list[FetchFormat] = field(
        default_factory=lambda: [FetchFormat.JSON, FetchFormat.XML]
    )

    # Error handling
    stop_on_error: bool = False  # If True, stop on first error

    # Storage
    store_raw_documents: bool = True  # Store raw JSON/XML in database


# Progress callback type
ProgressCallback = Callable[["ProgressUpdate"], None]


@dataclass
class ProgressUpdate:
    """Progress update during pipeline execution."""
    dataset_id: str
    stage: PipelineStage
    current: int
    total: int
    success: bool = True
    error: Optional[str] = None
    from_cache: bool = False

    @property
    def progress_pct(self) -> float:
        return (self.current / self.total * 100) if self.total > 0 else 0


class ETLPipeline:
    """
    ETL Pipeline for CEH datasets.

    Orchestrates: fetch → parse → store

    Features:
    - Batch commits for safety + performance
    - Structured result reporting
    - Progress callbacks
    - Graceful error handling

    Example:
        pipeline = ETLPipeline(
            client=CEHCatalogueClient(cache_dir="./cache"),
            parser_registry=create_default_registry(),
            session_factory=session_factory,
        )

        result = await pipeline.run(dataset_ids)

        if result.failed:
            for f in result.failed:
                print(f"{f.dataset_id}: {f.error_message}")
    """

    def __init__(
        self,
        client: CEHCatalogueClient,
        parser_registry: ParserRegistry,
        session_factory: SessionFactory,
        config: Optional[PipelineConfig] = None,
    ):
        """
        Initialize the pipeline.

        Args:
            client: CEH catalogue client for fetching
            parser_registry: Registry of metadata parsers
            session_factory: Database session factory
            config: Pipeline configuration
        """
        self.client = client
        self.parser_registry = parser_registry
        self.session_factory = session_factory
        self.config = config or PipelineConfig()

    async def run(
        self,
        dataset_ids: list[str],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> PipelineResult:
        """
        Run the ETL pipeline for given dataset IDs.

        Args:
            dataset_ids: List of dataset UUIDs to process
            progress_callback: Optional callback for progress updates

        Returns:
            PipelineResult with successes and failures
        """
        result = PipelineResult()
        total = len(dataset_ids)

        # Process in batches for commit safety
        batch: list[ProcessedDataset] = []

        # Fetch all datasets (async, rate-limited)
        fetch_results = await self.client.fetch_all(
            dataset_ids,
            formats=self.config.formats,
        )

        # Create a map for easy lookup
        fetch_map: dict[str, DatasetFetchResult] = {
            r.dataset_id: r for r in fetch_results.successful
        }

        # Add fetch failures to result
        for fetch_failure in fetch_results.failed:
            processed = ProcessedDataset(
                dataset_id=fetch_failure.dataset_id,
                success=False,
                stage_completed=PipelineStage.FETCH,
                error_stage=PipelineStage.FETCH,
                error_message=fetch_failure.error,
            )
            processed.completed_at = datetime.utcnow()
            result.failed.append(processed)

            if progress_callback:
                progress_callback(ProgressUpdate(
                    dataset_id=fetch_failure.dataset_id,
                    stage=PipelineStage.FETCH,
                    current=len(result.successful) + len(result.failed),
                    total=total,
                    success=False,
                    error=fetch_failure.error,
                ))

        # Process each successful fetch
        for i, dataset_id in enumerate(dataset_ids):
            if dataset_id not in fetch_map:
                continue  # Already recorded as fetch failure

            fetch_result = fetch_map[dataset_id]
            processed = await self._process_dataset(fetch_result)

            if processed.success:
                batch.append(processed)
            else:
                result.failed.append(processed)

                if self.config.stop_on_error:
                    break

            # Progress callback
            if progress_callback:
                progress_callback(ProgressUpdate(
                    dataset_id=dataset_id,
                    stage=processed.stage_completed,
                    current=len(result.successful) + len(result.failed) + len(batch),
                    total=total,
                    success=processed.success,
                    error=processed.error_message,
                    from_cache=processed.from_cache,
                ))

            # Commit batch if full
            if len(batch) >= self.config.batch_size:
                committed = await self._commit_batch(batch)
                result.successful.extend(committed)
                result.batches_committed += 1
                batch = []

        # Commit remaining batch
        if batch:
            committed = await self._commit_batch(batch)
            result.successful.extend(committed)
            result.batches_committed += 1

        result.completed_at = datetime.utcnow()
        return result

    async def _process_dataset(
        self,
        fetch_result: DatasetFetchResult,
    ) -> ProcessedDataset:
        """
        Process a single fetched dataset (parse only, no commit).

        Args:
            fetch_result: Result from fetching the dataset

        Returns:
            ProcessedDataset ready for batched commit
        """
        processed = ProcessedDataset(
            dataset_id=fetch_result.dataset_id,
            success=False,
            stage_completed=PipelineStage.FETCH,
            from_cache=fetch_result.from_cache,
        )

        try:
            # Parse JSON content
            if not fetch_result.json_content:
                raise ValueError("No JSON content available")

            # Parse returns DatasetMetadata directly (not a result wrapper)
            metadata = self.parser_registry.parse(
                fetch_result.json_content,
                content_type="application/json",
            )

            # Attach raw documents if configured
            if self.config.store_raw_documents:
                metadata.raw_document = fetch_result.json_content
                metadata.source_format = "json"

            processed.metadata = metadata
            processed.stage_completed = PipelineStage.PARSE
            processed.success = True

        except Exception as e:
            processed.error_stage = PipelineStage.PARSE
            processed.error_message = str(e)
            processed.error_traceback = traceback.format_exc()

        processed.completed_at = datetime.utcnow()
        return processed

    async def _commit_batch(
        self,
        batch: list[ProcessedDataset],
    ) -> list[ProcessedDataset]:
        """
        Commit a batch of processed datasets to the database.

        Args:
            batch: List of successfully parsed datasets

        Returns:
            List of successfully stored datasets
        """
        stored: list[ProcessedDataset] = []

        with UnitOfWork(self.session_factory) as uow:
            for processed in batch:
                try:
                    if processed.metadata:
                        uow.datasets.save(processed.metadata)
                        processed.stage_completed = PipelineStage.STORE
                        stored.append(processed)
                except Exception as e:
                    processed.success = False
                    processed.error_stage = PipelineStage.STORE
                    processed.error_message = str(e)
                    processed.error_traceback = traceback.format_exc()

            uow.commit()

        return stored

    async def run_single(self, dataset_id: str) -> ProcessedDataset:
        """
        Process a single dataset (convenience method).

        Args:
            dataset_id: Dataset UUID

        Returns:
            ProcessedDataset
        """
        result = await self.run([dataset_id])

        if result.successful:
            return result.successful[0]
        elif result.failed:
            return result.failed[0]
        else:
            return ProcessedDataset(
                dataset_id=dataset_id,
                success=False,
                stage_completed=PipelineStage.FETCH,
                error_message="Unknown error",
            )


# =============================================================================
# Console Progress Display
# =============================================================================

def create_console_progress() -> ProgressCallback:
    """Create a progress callback that prints to console."""
    last_len = 0

    def callback(update: ProgressUpdate) -> None:
        nonlocal last_len

        icons = {
            PipelineStage.FETCH: "📥",
            PipelineStage.PARSE: "🔍",
            PipelineStage.STORE: "💾",
            PipelineStage.COMPLETE: "✅" if update.success else "❌",
        }
        icon = icons.get(update.stage, "⏳")
        cache_indicator = " (cached)" if update.from_cache else ""

        bar_width = 30
        filled = int(bar_width * update.current / update.total)
        bar = "█" * filled + "░" * (bar_width - filled)

        line = (
            f"\r{icon} [{bar}] {update.progress_pct:5.1f}% "
            f"({update.current}/{update.total}) "
            f"{update.dataset_id[:8]}...{cache_indicator}"
        )

        padding = " " * max(0, last_len - len(line))
        print(line + padding, end="", flush=True)
        last_len = len(line)

        if update.current == update.total:
            print()

    return callback


# =============================================================================
# Checkpoint Support (for resumable pipelines)
# =============================================================================

@dataclass
class Checkpoint:
    """Checkpoint for resumable pipeline runs."""

    processed_ids: set[str] = field(default_factory=set)
    failed_ids: set[str] = field(default_factory=set)
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def save(self, path: Path) -> None:
        """Save checkpoint to file."""
        data = {
            "processed_ids": list(self.processed_ids),
            "failed_ids": list(self.failed_ids),
            "last_updated": self.last_updated.isoformat(),
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "Checkpoint":
        """Load checkpoint from file."""
        if not path.exists():
            return cls()

        data = json.loads(path.read_text())
        return cls(
            processed_ids=set(data.get("processed_ids", [])),
            failed_ids=set(data.get("failed_ids", [])),
            last_updated=datetime.fromisoformat(data["last_updated"]),
        )

    def remaining(self, all_ids: list[str]) -> list[str]:
        """Get IDs that haven't been processed yet."""
        return [
            id for id in all_ids
            if id not in self.processed_ids and id not in self.failed_ids
        ]


class ResumableETLPipeline(ETLPipeline):
    """
    ETL Pipeline with checkpoint support for resumable runs.

    Saves progress to disk so pipeline can be resumed after crashes.

    Example:
        pipeline = ResumableETLPipeline(
            client=client,
            parser_registry=create_default_registry(),
            session_factory=session_factory,
            checkpoint_path=Path("./checkpoints/etl_run.json"),
        )

        # First run - processes all
        result = await pipeline.run(dataset_ids)

        # If crashed, second run continues from checkpoint
        result = await pipeline.run(dataset_ids)
    """

    def __init__(
        self,
        client: CEHCatalogueClient,
        parser_registry: ParserRegistry,
        session_factory: SessionFactory,
        checkpoint_path: Path,
        config: Optional[PipelineConfig] = None,
    ):
        super().__init__(client, parser_registry, session_factory, config)
        self.checkpoint_path = checkpoint_path
        self.checkpoint = Checkpoint.load(checkpoint_path)

    async def run(
        self,
        dataset_ids: list[str],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> PipelineResult:
        """Run pipeline, skipping already-processed datasets."""

        # Filter to remaining IDs
        remaining = self.checkpoint.remaining(dataset_ids)

        if not remaining:
            return PipelineResult()  # Nothing to do

        # Run the base pipeline
        result = await super().run(remaining, progress_callback)

        # Update checkpoint
        for processed in result.successful:
            self.checkpoint.processed_ids.add(processed.dataset_id)
        for processed in result.failed:
            self.checkpoint.failed_ids.add(processed.dataset_id)

        self.checkpoint.last_updated = datetime.utcnow()
        self.checkpoint.save(self.checkpoint_path)

        return result

    def reset_checkpoint(self) -> None:
        """Reset checkpoint to start fresh."""
        self.checkpoint = Checkpoint()
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()