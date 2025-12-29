# Production ETL Pipeline Implementation Guide

## Overview

This guide provides a complete implementation for building production-quality ETL pipelines with proper error handling, retry strategies, structured logging, and progress tracking. The approach separates production-quality ETL from scripts that break in real-world conditions.

## 1. Partial Failure Strategy

**Answer: Continue processing, collect failures, report at end.**

Stopping on first failure is almost never correct for batch ETL. Your 212 datasets are independent — failure on dataset 47 tells you nothing about dataset 48.

### Strategy Comparison

| Strategy | When to Use |
|----------|------------|
| Fail fast | Data integrity critical (financial transactions), dependencies between records |
| Continue + collect | Independent records, batch processing, data ingestion ← **Your case** |
| Continue + quarantine | Need to reprocess failures separately |

### Implementation: Pipeline Result Structure

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import list

@dataclass
class PipelineResult:
    """Result of processing multiple datasets."""
    successful: list[DatasetMetadata]
    failed: list[FailedDataset]
    skipped: list[SkippedDataset]
    
    started_at: datetime
    completed_at: datetime
    
    @property
    def success_rate(self) -> float:
        total = len(self.successful) + len(self.failed)
        return len(self.successful) / total if total > 0 else 0.0
    
    @property
    def duration(self) -> timedelta:
        return self.completed_at - self.started_at
    
    def summary(self) -> str:
        return (
            f"Processed {len(self.successful) + len(self.failed)} datasets: "
            f"{len(self.successful)} succeeded, {len(self.failed)} failed "
            f"({self.success_rate:.1%}) in {self.duration.total_seconds():.1f}s"
        )


@dataclass
class FailedDataset:
    """Record of a failed dataset for debugging."""
    dataset_id: str
    stage: str  # "fetch", "parse", "store", "embed"
    error_type: str
    error_message: str
    attempts: int
    first_attempt: datetime
    last_attempt: datetime
    traceback: str | None = None
    
    def to_dict(self) -> dict:
        """For JSON serialization."""
        return {
            "dataset_id": self.dataset_id,
            "stage": self.stage,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "attempts": self.attempts,
            "timestamp": self.last_attempt.isoformat(),
        }
```

## 2. Retry Strategy

**Answer: Exponential backoff with jitter, configurable per error type.**

### Implementation: Retry Handler

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable, TypeVar
import asyncio
import random

T = TypeVar('T')


class RetryCategory(Enum):
    """Categorize errors by retry behavior."""
    TRANSIENT = "transient"      # Retry with backoff
    PERMANENT = "permanent"       # Don't retry
    RATE_LIMITED = "rate_limited" # Retry with longer delay


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0       # seconds
    max_delay: float = 60.0       # seconds
    exponential_base: float = 2.0
    jitter: float = 0.1           # ±10% randomization
    
    # Error classification
    transient_errors: set[type] = field(default_factory=lambda: {
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    })
    
    transient_status_codes: set[int] = field(default_factory=lambda: {
        408,  # Request Timeout
        429,  # Too Many Requests
        500,  # Internal Server Error
        502,  # Bad Gateway
        503,  # Service Unavailable
        504,  # Gateway Timeout
    })
    
    def classify_error(self, error: Exception, status_code: int | None = None) -> RetryCategory:
        """Determine if an error is retryable."""
        if status_code == 429:
            return RetryCategory.RATE_LIMITED
        
        if status_code and status_code in self.transient_status_codes:
            return RetryCategory.TRANSIENT
        
        if type(error) in self.transient_errors:
            return RetryCategory.TRANSIENT
        
        # Check inheritance
        for transient_type in self.transient_errors:
            if isinstance(error, transient_type):
                return RetryCategory.TRANSIENT
        
        return RetryCategory.PERMANENT
    
    def get_delay(self, attempt: int, category: RetryCategory) -> float:
        """Calculate delay before next retry."""
        if category == RetryCategory.RATE_LIMITED:
            # Longer delay for rate limiting
            base = self.base_delay * 5
        else:
            base = self.base_delay
        
        # Exponential backoff
        delay = base * (self.exponential_base ** attempt)
        
        # Cap at maximum
        delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)


class RetryHandler:
    """Handles retry logic for operations."""
    
    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()
    
    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        context: str = "operation",
    ) -> tuple[T | None, list[Exception]]:
        """
        Execute operation with retries.
        
        Returns:
            Tuple of (result, list of errors encountered)
            Result is None if all attempts failed
        """
        errors: list[Exception] = []
        
        for attempt in range(self.config.max_attempts):
            try:
                result = await operation()
                return result, errors
                
            except Exception as e:
                errors.append(e)
                
                # Classify the error
                status_code = getattr(e, 'status_code', None)
                category = self.config.classify_error(e, status_code)
                
                if category == RetryCategory.PERMANENT:
                    # Don't retry permanent errors
                    break
                
                if attempt < self.config.max_attempts - 1:
                    delay = self.config.get_delay(attempt, category)
                    await asyncio.sleep(delay)
        
        return None, errors
```

## 3. Structured Logging

**Answer: Use structlog for ETL pipelines.**

### Why Structured Logging Beats Standard Logging for ETL

| Feature | Standard logging | structlog |
|---------|-----------------|-----------|
| Machine parseable | ❌ Text parsing | ✅ JSON native |
| Context binding | Manual formatting | ✅ Automatic |
| Correlation IDs | DIY | ✅ Built-in |
| Log aggregation | Harder | ✅ Easy (ELK, Datadog) |
| Performance analysis | Manual | ✅ Structured fields |

### Implementation: ETL Logger

```python
import structlog
import logging
from contextvars import ContextVar

# Context variable for request/pipeline tracking
pipeline_context: ContextVar[dict] = ContextVar('pipeline_context', default={})


def configure_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: str | None = None,
) -> None:
    """Configure structured logging for ETL pipeline."""
    
    processors = [
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add log level
        structlog.stdlib.add_log_level,
        # Add context from context var
        structlog.contextvars.merge_contextvars,
        # Add exception info
        structlog.processors.format_exc_info,
    ]
    
    if json_output:
        # JSON output for production
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Pretty console output for development
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Create logger with bound context
def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger with automatic context binding."""
    return structlog.get_logger(name)


class ETLLogger:
    """Structured logging for ETL operations."""
    
    def __init__(self):
        self.log = get_logger("etl")
    
    def pipeline_started(self, total_datasets: int, config: dict):
        self.log.info(
            "pipeline_started",
            total_datasets=total_datasets,
            config=config,
        )
    
    def dataset_started(self, dataset_id: str, index: int, total: int):
        self.log.info(
            "dataset_processing_started",
            dataset_id=dataset_id,
            progress=f"{index}/{total}",
            progress_pct=round(index / total * 100, 1),
        )
    
    def dataset_fetched(self, dataset_id: str, format: str, size_bytes: int, duration_ms: float):
        self.log.debug(
            "dataset_fetched",
            dataset_id=dataset_id,
            format=format,
            size_bytes=size_bytes,
            duration_ms=round(duration_ms, 2),
        )
    
    def dataset_failed(
        self,
        dataset_id: str,
        stage: str,
        error: Exception,
        attempts: int,
    ):
        self.log.error(
            "dataset_processing_failed",
            dataset_id=dataset_id,
            stage=stage,
            error_type=type(error).__name__,
            error_message=str(error),
            attempts=attempts,
            exc_info=error,
        )
    
    def dataset_completed(self, dataset_id: str, duration_ms: float):
        self.log.info(
            "dataset_processing_completed",
            dataset_id=dataset_id,
            duration_ms=round(duration_ms, 2),
        )
    
    def pipeline_completed(self, result: 'PipelineResult'):
        self.log.info(
            "pipeline_completed",
            total_processed=len(result.successful) + len(result.failed),
            successful=len(result.successful),
            failed=len(result.failed),
            success_rate=round(result.success_rate * 100, 1),
            duration_seconds=result.duration.total_seconds(),
        )
```

### Sample Log Output (JSON Mode)

```json
{"timestamp": "2025-01-05T14:23:45.123Z", "level": "info", "event": "dataset_processing_started", "dataset_id": "be0bdc0e-bc2e-4f1d-b524-2c02798dd893", "progress": "47/212", "progress_pct": 22.2}
{"timestamp": "2025-01-05T14:23:45.456Z", "level": "debug", "event": "dataset_fetched", "dataset_id": "be0bdc0e-bc2e-4f1d-b524-2c02798dd893", "format": "json", "size_bytes": 45234, "duration_ms": 234.5}
{"timestamp": "2025-01-05T14:23:45.789Z", "level": "error", "event": "dataset_processing_failed", "dataset_id": "af6c4679-99aa-4352-9f63-af3bd7bc87a4", "stage": "fetch", "error_type": "TimeoutError", "error_message": "Connection timed out", "attempts": 3}
```

## 4. Progress Tracking

**Answer: Callback-based progress reporting for flexibility.**

### Implementation: Progress Callbacks

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class ProgressStage(Enum):
    """Stages of dataset processing."""
    FETCHING = "fetching"
    PARSING = "parsing"
    STORING = "storing"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProgressUpdate:
    """Progress update for a single dataset."""
    dataset_id: str
    stage: ProgressStage
    current_index: int
    total_count: int
    message: str | None = None
    error: str | None = None
    
    @property
    def progress_pct(self) -> float:
        return (self.current_index / self.total_count * 100) if self.total_count > 0 else 0


class ProgressCallback(ABC):
    """Abstract callback for progress reporting."""
    
    @abstractmethod
    def on_progress(self, update: ProgressUpdate) -> None:
        """Called when progress is made."""
        pass
    
    def on_pipeline_start(self, total: int) -> None:
        """Called when pipeline starts."""
        pass
    
    def on_pipeline_complete(self, result: 'PipelineResult') -> None:
        """Called when pipeline completes."""
        pass


class ConsoleProgressCallback(ProgressCallback):
    """Display progress in console with progress bar."""
    
    def __init__(self, show_bar: bool = True):
        self.show_bar = show_bar
        self._last_line_length = 0
    
    def on_pipeline_start(self, total: int) -> None:
        print(f"\n🚀 Starting ETL pipeline for {total} datasets\n")
    
    def on_progress(self, update: ProgressUpdate) -> None:
        if self.show_bar:
            self._print_progress_bar(update)
        else:
            self._print_simple(update)
    
    def _print_progress_bar(self, update: ProgressUpdate) -> None:
        """Print a progress bar that updates in place."""
        bar_width = 40
        filled = int(bar_width * update.current_index / update.total_count)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        status_icon = {
            ProgressStage.FETCHING: "📥",
            ProgressStage.PARSING: "🔍",
            ProgressStage.STORING: "💾",
            ProgressStage.EMBEDDING: "🧠",
            ProgressStage.COMPLETED: "✅",
            ProgressStage.FAILED: "❌",
        }.get(update.stage, "⏳")
        
        line = (
            f"\r{status_icon} [{bar}] {update.progress_pct:5.1f}% "
            f"({update.current_index}/{update.total_count}) "
            f"{update.stage.value}: {update.dataset_id[:8]}..."
        )
        
        # Clear previous line if shorter
        padding = " " * max(0, self._last_line_length - len(line))
        print(line + padding, end="", flush=True)
        self._last_line_length = len(line)
        
        if update.stage in (ProgressStage.COMPLETED, ProgressStage.FAILED):
            if update.current_index == update.total_count:
                print()  # Newline at end
    
    def _print_simple(self, update: ProgressUpdate) -> None:
        """Print simple line-by-line progress."""
        print(f"[{update.current_index}/{update.total_count}] {update.stage.value}: {update.dataset_id}")
    
    def on_pipeline_complete(self, result: 'PipelineResult') -> None:
        print(f"\n✨ {result.summary()}")
        
        if result.failed:
            print(f"\n❌ Failed datasets ({len(result.failed)}):")
            for failed in result.failed[:5]:  # Show first 5
                print(f"   • {failed.dataset_id}: {failed.error_message}")
            if len(result.failed) > 5:
                print(f"   ... and {len(result.failed) - 5} more")


class LoggingProgressCallback(ProgressCallback):
    """Log progress using structured logging."""
    
    def __init__(self, logger: ETLLogger):
        self.logger = logger
    
    def on_pipeline_start(self, total: int) -> None:
        self.logger.pipeline_started(total, {})
    
    def on_progress(self, update: ProgressUpdate) -> None:
        if update.stage == ProgressStage.FAILED:
            self.logger.log.warning(
                "dataset_progress",
                dataset_id=update.dataset_id,
                stage=update.stage.value,
                error=update.error,
            )
        else:
            self.logger.log.debug(
                "dataset_progress",
                dataset_id=update.dataset_id,
                stage=update.stage.value,
                progress_pct=update.progress_pct,
            )
    
    def on_pipeline_complete(self, result: 'PipelineResult') -> None:
        self.logger.pipeline_completed(result)


class CompositeProgressCallback(ProgressCallback):
    """Combine multiple progress callbacks."""
    
    def __init__(self, callbacks: list[ProgressCallback]):
        self.callbacks = callbacks
    
    def on_pipeline_start(self, total: int) -> None:
        for callback in self.callbacks:
            callback.on_pipeline_start(total)
    
    def on_progress(self, update: ProgressUpdate) -> None:
        for callback in self.callbacks:
            callback.on_progress(update)
    
    def on_pipeline_complete(self, result: 'PipelineResult') -> None:
        for callback in self.callbacks:
            callback.on_pipeline_complete(result)
```

## 5. Complete ETL Orchestrator

Putting it all together with the complete orchestrator implementation:

```python
import traceback
from datetime import datetime


class ETLOrchestrator:
    """
    Orchestrates the ETL pipeline with error handling and progress tracking.
    
    Design principles:
    - Continue on failure (collect errors)
    - Retry transient errors with backoff
    - Structured logging throughout
    - Pluggable progress callbacks
    """
    
    def __init__(
        self,
        resource_factory: ResourceFactory,
        parser_factory: ParserFactory,
        repository: DatasetRepository,
        retry_config: RetryConfig | None = None,
        progress_callback: ProgressCallback | None = None,
    ):
        self.resources = resource_factory
        self.parsers = parser_factory
        self.repository = repository
        self.retry = RetryHandler(retry_config)
        self.progress = progress_callback or ConsoleProgressCallback()
        self.logger = ETLLogger()
    
    async def process_datasets(
        self,
        dataset_ids: list[str],
        formats: list[str] | None = None,
    ) -> PipelineResult:
        """
        Process multiple datasets.
        
        Args:
            dataset_ids: List of dataset UUIDs to process
            formats: Formats to fetch (default: ["json"])
        
        Returns:
            PipelineResult with successes and failures
        """
        formats = formats or ["json"]
        total = len(dataset_ids)
        
        successful: list[DatasetMetadata] = []
        failed: list[FailedDataset] = []
        
        started_at = datetime.utcnow()
        self.progress.on_pipeline_start(total)
        
        for index, dataset_id in enumerate(dataset_ids, 1):
            try:
                metadata = await self._process_single_dataset(
                    dataset_id=dataset_id,
                    formats=formats,
                    index=index,
                    total=total,
                )
                successful.append(metadata)
                
                self.progress.on_progress(ProgressUpdate(
                    dataset_id=dataset_id,
                    stage=ProgressStage.COMPLETED,
                    current_index=index,
                    total_count=total,
                ))
                
            except Exception as e:
                failure = FailedDataset(
                    dataset_id=dataset_id,
                    stage=self._get_failure_stage(e),
                    error_type=type(e).__name__,
                    error_message=str(e),
                    attempts=getattr(e, 'attempts', 1),
                    first_attempt=started_at,
                    last_attempt=datetime.utcnow(),
                    traceback=traceback.format_exc(),
                )
                failed.append(failure)
                
                self.logger.dataset_failed(
                    dataset_id=dataset_id,
                    stage=failure.stage,
                    error=e,
                    attempts=failure.attempts,
                )
                
                self.progress.on_progress(ProgressUpdate(
                    dataset_id=dataset_id,
                    stage=ProgressStage.FAILED,
                    current_index=index,
                    total_count=total,
                    error=str(e),
                ))
        
        result = PipelineResult(
            successful=successful,
            failed=failed,
            skipped=[],
            started_at=started_at,
            completed_at=datetime.utcnow(),
        )
        
        self.progress.on_pipeline_complete(result)
        return result
    
    async def _process_single_dataset(
        self,
        dataset_id: str,
        formats: list[str],
        index: int,
        total: int,
    ) -> DatasetMetadata:
        """Process a single dataset with retries."""
        
        # Stage 1: Fetch
        self.progress.on_progress(ProgressUpdate(
            dataset_id=dataset_id,
            stage=ProgressStage.FETCHING,
            current_index=index,
            total_count=total,
        ))
        
        content, fetch_errors = await self.retry.execute(
            lambda: self._fetch_dataset(dataset_id, formats[0]),
            context=f"fetch:{dataset_id}",
        )
        
        if content is None:
            error = FetchError(f"Failed to fetch after retries: {fetch_errors[-1]}")
            error.attempts = len(fetch_errors)
            raise error
        
        # Stage 2: Parse
        self.progress.on_progress(ProgressUpdate(
            dataset_id=dataset_id,
            stage=ProgressStage.PARSING,
            current_index=index,
            total_count=total,
        ))
        
        parser = self.parsers.get_parser(formats[0])
        metadata = parser.parse(content)
        
        # Stage 3: Store
        self.progress.on_progress(ProgressUpdate(
            dataset_id=dataset_id,
            stage=ProgressStage.STORING,
            current_index=index,
            total_count=total,
        ))
        
        await self.repository.save(metadata)
        
        return metadata
    
    async def _fetch_dataset(self, dataset_id: str, format: str) -> str:
        """Fetch dataset content."""
        resource = self.resources.ceh_metadata(dataset_id, format=format)
        result = await resource.fetch()
        
        if not result.success:
            raise FetchError(result.error or "Unknown fetch error")
        
        return result.text
    
    def _get_failure_stage(self, error: Exception) -> str:
        """Determine which stage failed based on error type."""
        if isinstance(error, FetchError):
            return "fetch"
        elif isinstance(error, ParseError):
            return "parse"
        elif isinstance(error, StorageError):
            return "store"
        return "unknown"
```

## Usage Example

```python
async def main():
    # Configure structured logging
    configure_logging(
        level="INFO",
        json_output=True,  # Use JSON for production
    )
    
    # Setup retry configuration
    retry_config = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0,
        jitter=0.1,
    )
    
    # Setup progress callbacks
    progress = CompositeProgressCallback([
        ConsoleProgressCallback(show_bar=True),
        LoggingProgressCallback(ETLLogger()),
    ])
    
    # Create orchestrator
    orchestrator = ETLOrchestrator(
        resource_factory=ResourceFactory(),
        parser_factory=ParserFactory(),
        repository=DatasetRepository(),
        retry_config=retry_config,
        progress_callback=progress,
    )
    
    # Process datasets
    dataset_ids = ["uuid-1", "uuid-2", "uuid-3", ...]  # Your 212 datasets
    result = await orchestrator.process_datasets(dataset_ids)
    
    # Handle results
    print(result.summary())
    
    if result.failed:
        # Save failed datasets for retry
        with open("failed_datasets.json", "w") as f:
            json.dump([f.to_dict() for f in result.failed], f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
```

## Summary of Recommendations

| Concern | Recommendation |
|---------|---------------|
| Partial failures | Continue processing, collect `FailedDataset` records |
| Retry strategy | Exponential backoff with jitter, classify errors by type |
| Logging | `structlog` with JSON output for production |
| Progress | Callback-based system for flexibility (console, logging, or both) |

This approach ensures your ETL pipeline is production-ready with:
- **Resilience**: Continues processing even when individual datasets fail
- **Debuggability**: Structured logging and detailed error tracking
- **Observability**: Real-time progress updates and comprehensive result reporting
- **Scalability**: Handles transient failures gracefully with intelligent retries