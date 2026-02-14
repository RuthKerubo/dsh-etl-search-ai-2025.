"""
Domain models for the ETL pipeline.

This module provides two layers of models:

1. Domain Models (Pydantic)
   - DatasetMetadata, BoundingBox, etc.
   - Used by parsers and business logic
   - Handle validation and serialization

2. ORM Models (SQLAlchemy)
   - Dataset, Keyword, Distribution, etc.
   - Handle database persistence
   - Managed by the repository layer

Converters are provided to translate between the two layers.
"""

# Domain models (Pydantic)
from .dataset import (
    # Enums
    AccessType,
    RelationshipType,
    ResponsiblePartyRole,
    TopicCategory,
    # Component models
    BoundingBox,
    DistributionInfo,
    RelatedDocument,
    ResponsibleParty,
    SupportingDocument,
    TemporalExtent,
    # Main model
    DatasetMetadata,
    # Factory functions
    create_minimal_dataset,
)

# ORM models (SQLAlchemy)
from .orm import (
    Base,
    Dataset,
    DatasetKeyword,
    DatasetResponsibleParty,
    Distribution,
    EmbeddingRecord,
    Keyword,
    RawDocument,
    RelatedDocument as RelatedDocumentORM,
    ResponsibleParty as ResponsiblePartyORM,
    SupportingDocument as SupportingDocumentORM,
    create_database,
    get_engine,
)

# Converters
from .converters import (
    domain_to_orm,
    orm_to_domain,
    update_dataset_from_domain,
)

from .user import (
    User,
    UserCreate,
    UserUpdate,
    UserPreferences,
    SearchHistoryEntry,
)

__all__ = [
    # Domain Enums
    "AccessType",
    "RelationshipType",
    "ResponsiblePartyRole",
    "TopicCategory",
    # Domain Component models
    "BoundingBox",
    "DistributionInfo",
    "RelatedDocument",
    "ResponsibleParty",
    "SupportingDocument",
    "TemporalExtent",
    # Domain Main model
    "DatasetMetadata",
    # Domain Factory functions
    "create_minimal_dataset",
    # ORM Base
    "Base",
    # ORM Models
    "Dataset",
    "DatasetKeyword",
    "DatasetResponsibleParty",
    "Distribution",
    "EmbeddingRecord",
    "Keyword",
    "RawDocument",
    "RelatedDocumentORM",
    "ResponsiblePartyORM",
    "SupportingDocumentORM",
    # ORM Utilities
    "create_database",
    "get_engine",
    # Converters
    "domain_to_orm",
    "orm_to_domain",
    "update_dataset_from_domain",
    # ... Users ...
    "User",
    "UserCreate",
    "UserUpdate",
    "UserPreferences",
    "SearchHistoryEntry",
]