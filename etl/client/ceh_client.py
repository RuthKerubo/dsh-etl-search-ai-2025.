"""
ETL Client layer.

High-level clients for external data sources.
"""

from .ceh_client import (
    CEHCatalogueClient,
    BatchFetchResult,
    DatasetFetchResult,
    FetchFormat,
    FetchError,
    ProgressUpdate,
    create_console_progress,
    fetch_datasets,
)

__all__ = [
    "CEHCatalogueClient",
    "BatchFetchResult",
    "DatasetFetchResult",
    "FetchFormat",
    "FetchError",
    "ProgressUpdate",
    "create_console_progress",
    "fetch_datasets",
]