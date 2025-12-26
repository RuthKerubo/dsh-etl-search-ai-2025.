"""
Domain models for the ETL pipeline.

These Pydantic models provide the unified representation for all metadata,
regardless of source format. They are the "contract" between parsers
and the rest of the system.
"""

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

__all__ = [
    # Enums
    "AccessType",
    "RelationshipType",
    "ResponsiblePartyRole",
    "TopicCategory",
    # Component models
    "BoundingBox",
    "DistributionInfo",
    "RelatedDocument",
    "ResponsibleParty",
    "SupportingDocument",
    "TemporalExtent",
    # Main model
    "DatasetMetadata",
    # Factory functions
    "create_minimal_dataset",
]