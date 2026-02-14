"""
Domain models for dataset metadata.

These Pydantic models serve as the unified representation for all metadata,
regardless of source format (ISO 19115 XML, JSON, JSON-LD, RDF).

Based on ISO 19115 Geographic Metadata Standard with adaptations for
the CEH Catalogue structure.
"""

from datetime import date, datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =============================================================================
# Enumerations
# =============================================================================

class ResponsiblePartyRole(str, Enum):
    """
    Roles for responsible parties as defined in ISO 19115.

    Reference: ISO 19115-1:2014 B.3.2 CI_RoleCode
    """
    RESOURCE_PROVIDER = "resourceProvider"
    CUSTODIAN = "custodian"
    OWNER = "owner"
    USER = "user"
    DISTRIBUTOR = "distributor"
    ORIGINATOR = "originator"
    POINT_OF_CONTACT = "pointOfContact"
    PRINCIPAL_INVESTIGATOR = "principalInvestigator"
    PROCESSOR = "processor"
    PUBLISHER = "publisher"
    AUTHOR = "author"
    SPONSOR = "sponsor"
    CO_AUTHOR = "coAuthor"
    COLLABORATOR = "collaborator"
    EDITOR = "editor"
    MEDIATOR = "mediator"
    RIGHTS_HOLDER = "rightsHolder"
    CONTRIBUTOR = "contributor"
    FUNDER = "funder"
    STAKEHOLDER = "stakeholder"
    # Fallback for unknown roles
    OTHER = "other"


class AccessType(str, Enum):
    """Type of access for dataset distribution."""
    DOWNLOAD = "download"
    FILE_ACCESS = "fileAccess"
    ORDER = "order"
    OFFLINE = "offline"
    OTHER = "other"


class RelationshipType(str, Enum):
    """
    Types of relationships between documents/datasets.

    Reference: ISO 19115-1:2014 B.3.1 DS_AssociationTypeCode
    """
    PARENT = "parent"
    CHILD = "child"
    SIBLING = "sibling"
    CROSS_REFERENCE = "crossReference"
    SOURCE = "source"
    SERIES = "series"
    DEPENDENCY = "dependency"
    REVISION_OF = "revisionOf"
    PART_OF_SEAMLESS_DATABASE = "partOfSeamlessDatabase"
    STEREO_MATE = "stereoMate"
    IS_COMPOSED_OF = "isComposedOf"
    COLLECTIVE_TITLE = "collectiveTitle"
    LARGER_WORK_CITATION = "largerWorkCitation"
    # Fallback
    OTHER = "other"


class TopicCategory(str, Enum):
    """
    High-level topic categories as defined in ISO 19115.

    Reference: ISO 19115-1:2014 B.3.21 MD_TopicCategoryCode
    """
    FARMING = "farming"
    BIOTA = "biota"
    BOUNDARIES = "boundaries"
    CLIMATOLOGY_METEOROLOGY_ATMOSPHERE = "climatologyMeteorologyAtmosphere"
    ECONOMY = "economy"
    ELEVATION = "elevation"
    ENVIRONMENT = "environment"
    GEOSCIENTIFIC_INFORMATION = "geoscientificInformation"
    HEALTH = "health"
    IMAGERY_BASE_MAPS_EARTH_COVER = "imageryBaseMapsEarthCover"
    INTELLIGENCE_MILITARY = "intelligenceMilitary"
    INLAND_WATERS = "inlandWaters"
    LOCATION = "location"
    OCEANS = "oceans"
    PLANNING_CADASTRE = "planningCadastre"
    SOCIETY = "society"
    STRUCTURE = "structure"
    TRANSPORTATION = "transportation"
    UTILITIES_COMMUNICATION = "utilitiesCommunication"
    EXTRA_TERRESTRIAL = "extraTerrestrial"
    DISASTER = "disaster"


# =============================================================================
# Coordinate Types with Validation
# =============================================================================

# Annotated types for coordinate validation
Longitude = Annotated[
    float,
    Field(ge=-180.0, le=180.0, description="Longitude in WGS84 (-180 to 180)")
]

Latitude = Annotated[
    float,
    Field(ge=-90.0, le=90.0, description="Latitude in WGS84 (-90 to 90)")
]


# =============================================================================
# Component Models
# =============================================================================

class BoundingBox(BaseModel):
    """
    Geographic bounding box in WGS84 coordinates.

    Represents the spatial extent of a dataset as a rectangle
    defined by its corner coordinates.

    Attributes:
        west: Western-most longitude (-180 to 180)
        east: Eastern-most longitude (-180 to 180)
        south: Southern-most latitude (-90 to 90)
        north: Northern-most latitude (-90 to 90)
    """

    model_config = ConfigDict(
        frozen=False,  # Allow mutation if needed
        validate_assignment=True,
    )

    west: Longitude
    east: Longitude
    south: Latitude
    north: Latitude

    @model_validator(mode="after")
    def validate_bounds(self) -> "BoundingBox":
        """Validate that north is greater than or equal to south."""
        if self.north < self.south:
            raise ValueError(
                f"North ({self.north}) must be >= south ({self.south})"
            )
        return self

    @property
    def is_valid(self) -> bool:
        """Check if bounding box has valid, non-zero extent."""
        return (
            self.north >= self.south and
            abs(self.east - self.west) > 0 or
            abs(self.north - self.south) > 0
        )

    @property
    def center(self) -> tuple[float, float]:
        """Calculate center point (longitude, latitude)."""
        # Handle antimeridian crossing
        if self.east < self.west:
            center_lon = ((self.west + self.east + 360) / 2) % 360
            if center_lon > 180:
                center_lon -= 360
        else:
            center_lon = (self.west + self.east) / 2

        center_lat = (self.south + self.north) / 2
        return (center_lon, center_lat)


class TemporalExtent(BaseModel):
    """
    Temporal extent of a dataset.

    Represents the time period covered by the data. Either or both
    dates can be None to represent open-ended ranges.

    Examples:
        - Historical data: start_date=1990-01-01, end_date=2000-12-31
        - Ongoing collection: start_date=2020-01-01, end_date=None
        - Unknown start: start_date=None, end_date=2023-12-31

    Attributes:
        start_date: Beginning of the temporal extent (optional)
        end_date: End of the temporal extent (optional)
    """

    model_config = ConfigDict(
        validate_assignment=True,
    )

    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_order(self) -> "TemporalExtent":
        """Validate that end_date is not before start_date."""
        if (
            self.start_date is not None and
            self.end_date is not None and
            self.end_date < self.start_date
        ):
            raise ValueError(
                f"end_date ({self.end_date}) must be >= start_date ({self.start_date})"
            )
        return self

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_date(cls, value):
        """Parse date from various formats."""
        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y"]:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"Cannot parse date: {value}")
        return value

    @property
    def is_open_ended(self) -> bool:
        """Check if the temporal extent is open-ended."""
        return self.start_date is None or self.end_date is None

    @property
    def is_ongoing(self) -> bool:
        """Check if the dataset is still being updated (no end date)."""
        return self.start_date is not None and self.end_date is None


class ResponsibleParty(BaseModel):
    """
    Person or organisation responsible for the dataset.

    Represents a party with a specific role in relation to the dataset,
    as defined in ISO 19115 CI_Responsibility.

    Attributes:
        name: Name of the individual
        organisation: Name of the organisation
        role: Role of the party (e.g., publisher, author)
        email: Contact email address
        orcid: ORCID identifier for individuals
    """

    model_config = ConfigDict(
        validate_assignment=True,
    )

    name: str | None = None
    organisation: str | None = None
    role: ResponsiblePartyRole = ResponsiblePartyRole.OTHER
    email: str | None = None
    orcid: str | None = None

    @model_validator(mode="after")
    def validate_has_identity(self) -> "ResponsibleParty":
        """Ensure at least name or organisation is provided."""
        if not self.name and not self.organisation:
            raise ValueError("Either name or organisation must be provided")
        return self

    @field_validator("role", mode="before")
    @classmethod
    def parse_role(cls, value):
        """Parse role from string, handling unknown values."""
        if value is None:
            return ResponsiblePartyRole.OTHER
        if isinstance(value, ResponsiblePartyRole):
            return value
        if isinstance(value, str):
            # Try exact match
            try:
                return ResponsiblePartyRole(value)
            except ValueError:
                pass
            # Try case-insensitive match
            value_lower = value.lower().replace(" ", "").replace("_", "")
            for role in ResponsiblePartyRole:
                if role.value.lower().replace("_", "") == value_lower:
                    return role
            # Fallback to OTHER
            return ResponsiblePartyRole.OTHER
        return value

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, value):
        """Basic email validation."""
        if value is None or value == "":
            return None
        if isinstance(value, str) and "@" not in value:
            return None  # Invalid email, treat as missing
        return value

    @property
    def display_name(self) -> str:
        """Get a display name for the party."""
        if self.name and self.organisation:
            return f"{self.name} ({self.organisation})"
        return self.name or self.organisation or "Unknown"


class DistributionInfo(BaseModel):
    """
    Information about how to access/download the dataset.

    Represents a distribution option for the dataset, including
    the access URL, format, and access method.

    Attributes:
        url: URL for accessing the data
        name: Display name for this distribution
        format: File format or MIME type
        access_type: Type of access (download, fileAccess, etc.)
        size_bytes: Size in bytes (if known)
        description: Additional description
    """

    model_config = ConfigDict(
        validate_assignment=True,
    )

    url: str
    name: str | None = None
    format: str | None = None
    access_type: AccessType = AccessType.OTHER
    size_bytes: int | None = Field(default=None, ge=0)
    description: str | None = None

    @field_validator("access_type", mode="before")
    @classmethod
    def parse_access_type(cls, value):
        """Parse access type from string."""
        if value is None:
            return AccessType.OTHER
        if isinstance(value, AccessType):
            return value
        if isinstance(value, str):
            try:
                return AccessType(value)
            except ValueError:
                # Try case-insensitive match
                value_lower = value.lower().replace(" ", "").replace("_", "")
                for at in AccessType:
                    if at.value.lower() == value_lower:
                        return at
                return AccessType.OTHER
        return value

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, value):
        """Ensure URL is a non-empty string."""
        if not value or not isinstance(value, str):
            raise ValueError("URL is required")
        return value.strip()


class RelatedDocument(BaseModel):
    """
    Reference to a related document or dataset.

    Represents a relationship between this dataset and another
    document, such as a parent dataset, supporting document,
    or related publication.

    Attributes:
        identifier: Identifier of the related document (UUID or URL)
        relationship_type: Type of relationship
        title: Title of the related document (if known)
        url: URL to access the related document
    """

    model_config = ConfigDict(
        validate_assignment=True,
    )

    identifier: str
    relationship_type: RelationshipType = RelationshipType.OTHER
    title: str | None = None
    url: str | None = None

    @field_validator("relationship_type", mode="before")
    @classmethod
    def parse_relationship_type(cls, value):
        """Parse relationship type from string."""
        if value is None:
            return RelationshipType.OTHER
        if isinstance(value, RelationshipType):
            return value
        if isinstance(value, str):
            try:
                return RelationshipType(value)
            except ValueError:
                # Try case-insensitive match
                value_lower = value.lower().replace(" ", "").replace("_", "")
                for rt in RelationshipType:
                    if rt.value.lower().replace("_", "") == value_lower:
                        return rt
                return RelationshipType.OTHER
        return value


class SupportingDocument(BaseModel):
    """
    Supporting document associated with a dataset.

    Represents additional documentation such as methodology reports,
    data dictionaries, or publications.

    Attributes:
        filename: Name of the file
        url: URL to download the document
        content_type: MIME type of the document
        size_bytes: Size in bytes
        description: Description of the document
        extracted_text: Text extracted from document (for RAG)
    """

    model_config = ConfigDict(
        validate_assignment=True,
    )

    filename: str
    url: str | None = None
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    description: str | None = None
    extracted_text: str | None = None


# =============================================================================
# Main Dataset Model
# =============================================================================

class DatasetMetadata(BaseModel):
    """
    Unified dataset metadata model.

    This is the canonical representation of dataset metadata that all
    parsers produce, regardless of the source format (ISO 19115 XML,
    CEH JSON, JSON-LD, or RDF).

    Based on ISO 19115-1:2014 Geographic Metadata Standard with
    adaptations for the CEH Environmental Data Centre.

    Attributes:
        identifier: Unique identifier (UUID) for the dataset
        title: Title of the dataset
        abstract: Description/abstract of the dataset
        keywords: List of keywords/tags
        topic_categories: ISO 19115 topic categories
        bounding_box: Geographic extent
        temporal_extent: Time period covered
        lineage: Information about data provenance
        responsible_parties: People/organisations involved
        distributions: Access/download options
        related_documents: Links to related datasets/documents
        supporting_documents: Associated documentation
        source_format: Original metadata format
        raw_document: Original document content (for reference)
    """

    model_config = ConfigDict(
        validate_assignment=True,
        use_enum_values=True,  # Serialize enums as their values
    )

    # -------------------------------------------------------------------------
    # Required Fields
    # -------------------------------------------------------------------------
    identifier: str = Field(
        ...,
        min_length=1,
        description="Unique identifier (UUID) for the dataset"
    )
    title: str = Field(
        ...,
        min_length=1,
        description="Title of the dataset"
    )

    # -------------------------------------------------------------------------
    # Optional Text Fields
    # -------------------------------------------------------------------------
    abstract: str | None = Field(
        default=None,
        description="Description/abstract of the dataset"
    )
    lineage: str | None = Field(
        default=None,
        description="Information about data provenance and processing"
    )

    # -------------------------------------------------------------------------
    # Classification
    # -------------------------------------------------------------------------
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords/tags for discovery"
    )
    topic_categories: list[TopicCategory] = Field(
        default_factory=list,
        description="ISO 19115 topic categories"
    )

    # -------------------------------------------------------------------------
    # Spatial and Temporal Extent
    # -------------------------------------------------------------------------
    bounding_box: BoundingBox | None = Field(
        default=None,
        description="Geographic bounding box in WGS84"
    )
    temporal_extent: TemporalExtent | None = Field(
        default=None,
        description="Time period covered by the dataset"
    )

    # -------------------------------------------------------------------------
    # Parties and Access
    # -------------------------------------------------------------------------
    responsible_parties: list[ResponsibleParty] = Field(
        default_factory=list,
        description="People/organisations responsible for the dataset"
    )
    distributions: list[DistributionInfo] = Field(
        default_factory=list,
        description="Access/download options"
    )

    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    related_documents: list[RelatedDocument] = Field(
        default_factory=list,
        description="Links to related datasets/documents"
    )
    supporting_documents: list[SupportingDocument] = Field(
        default_factory=list,
        description="Associated documentation files"
    )

    # -------------------------------------------------------------------------
    # Metadata about the Metadata
    # -------------------------------------------------------------------------
    source_format: str | None = Field(
        default=None,
        description="Original metadata format (iso19115, json, jsonld, rdf)"
    )
    raw_document: str | None = Field(
        default=None,
        description="Original document content for reference",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------

    @field_validator("keywords", mode="before")
    @classmethod
    def clean_keywords(cls, value):
        """Clean and deduplicate keywords."""
        if value is None:
            return []
        if isinstance(value, str):
            # Handle comma-separated string
            value = [k.strip() for k in value.split(",")]
        # Remove empty strings and duplicates while preserving order
        seen = set()
        cleaned = []
        for kw in value:
            if kw and kw not in seen:
                seen.add(kw)
                cleaned.append(kw)
        return cleaned

    @field_validator("topic_categories", mode="before")
    @classmethod
    def parse_topic_categories(cls, value):
        """Parse topic categories from various formats."""
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]

        categories = []
        for cat in value:
            if isinstance(cat, TopicCategory):
                categories.append(cat)
            elif isinstance(cat, str):
                try:
                    categories.append(TopicCategory(cat))
                except ValueError:
                    # Try case-insensitive match
                    cat_lower = cat.lower().replace(" ", "").replace("_", "")
                    for tc in TopicCategory:
                        if tc.value.lower().replace("_", "") == cat_lower:
                            categories.append(tc)
                            break
        return categories

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    @property
    def has_spatial_extent(self) -> bool:
        """Check if dataset has spatial extent defined."""
        return self.bounding_box is not None

    @property
    def has_temporal_extent(self) -> bool:
        """Check if dataset has temporal extent defined."""
        return self.temporal_extent is not None

    @property
    def has_downloads(self) -> bool:
        """Check if dataset has download options."""
        return any(
            d.access_type == AccessType.DOWNLOAD
            for d in self.distributions
        )

    @property
    def publisher(self) -> ResponsibleParty | None:
        """Get the publisher if one exists."""
        for party in self.responsible_parties:
            if party.role == ResponsiblePartyRole.PUBLISHER:
                return party
        return None

    @property
    def search_text(self) -> str:
        """
        Combine title, abstract, and keywords for embedding.

        This is the text that will be embedded for semantic search.
        """
        parts = [self.title]
        if self.abstract:
            parts.append(self.abstract)
        if self.keywords:
            parts.append(" ".join(self.keywords))
        return " ".join(parts)

    def to_dict(self, include_raw: bool = False) -> dict:
        """
        Convert to dictionary for database storage.

        Args:
            include_raw: Whether to include raw_document field

        Returns:
            Dictionary representation
        """
        exclude_fields = {"raw_document"} if not include_raw else None
        return self.model_dump(mode="json", exclude=exclude_fields)

    @classmethod
    def from_dict(cls, data: dict) -> "DatasetMetadata":
        """
        Create instance from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            DatasetMetadata instance
        """
        return cls.model_validate(data)


# =============================================================================
# Factory Functions
# =============================================================================

def create_minimal_dataset(
    identifier: str,
    title: str,
    abstract: str | None = None,
) -> DatasetMetadata:
    """
    Create a minimal dataset with only required fields.

    Useful for testing or creating placeholder records.

    Args:
        identifier: Dataset UUID
        title: Dataset title
        abstract: Optional abstract

    Returns:
        DatasetMetadata instance
    """
    return DatasetMetadata(
        identifier=identifier,
        title=title,
        abstract=abstract,
    )