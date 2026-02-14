"""
Converters between Pydantic domain models and SQLAlchemy ORM models.

These functions handle the translation between the domain layer
(Pydantic models used by parsers) and the persistence layer
(SQLAlchemy models used by the database).

This separation allows:
- Domain models to focus on validation and business logic
- ORM models to focus on database mapping
- Easy testing of either layer independently
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

from .dataset import (
    AccessType,
    BoundingBox,
    DatasetMetadata,
    DistributionInfo,
    RelatedDocument as DomainRelatedDocument,
    RelationshipType,
    ResponsibleParty as DomainResponsibleParty,
    ResponsiblePartyRole,
    SupportingDocument as DomainSupportingDocument,
    TemporalExtent,
    TopicCategory,
)
from .orm import (
    Dataset,
    DatasetResponsibleParty,
    Distribution,
    EmbeddingRecord,
    Keyword,
    RawDocument,
    RelatedDocument,
    ResponsibleParty,
    SupportingDocument,
)
from etl.models import dataset


# =============================================================================
# Domain -> ORM Converters
# =============================================================================

def domain_to_orm(
    domain: DatasetMetadata,
    session: Session,
    include_raw: bool = True,
) -> Dataset:
    """
    Convert a Pydantic DatasetMetadata to SQLAlchemy Dataset.

    Handles:
    - Creating or finding existing keywords (M:N)
    - Creating or finding existing responsible parties (M:N)
    - Creating distribution, related doc, supporting doc records (1:N)
    - Storing raw document if provided

    Args:
        domain: Pydantic domain model
        session: SQLAlchemy session for lookups
        include_raw: Whether to store raw document

    Returns:
        SQLAlchemy Dataset instance (not yet committed)
    """
    # Create main dataset record
    dataset = Dataset(
        identifier=domain.identifier,
        title=domain.title,
        abstract=domain.abstract,
        lineage=domain.lineage,
        topic_categories=json.dumps([tc.value if isinstance(tc, TopicCategory) else tc
                                     for tc in domain.topic_categories]) if domain.topic_categories else None,
    )

    # Embed bounding box
    if domain.bounding_box:
        dataset.bbox_west = domain.bounding_box.west
        dataset.bbox_east = domain.bounding_box.east
        dataset.bbox_south = domain.bounding_box.south
        dataset.bbox_north = domain.bounding_box.north

    # Embed temporal extent
    if domain.temporal_extent:
        dataset.temporal_start = domain.temporal_extent.start_date
        dataset.temporal_end = domain.temporal_extent.end_date

    # Use no_autoflush to prevent premature flush during lookups
    with session.no_autoflush:
        # Handle keywords (M:N) - find or create
        for kw_text in domain.keywords:
            keyword = session.query(Keyword).filter_by(keyword=kw_text).first()
            if not keyword:
                keyword = Keyword(keyword=kw_text)
                session.add(keyword)
            dataset.keywords.append(keyword)

        # Handle responsible parties (M:N with role)
        # Deduplicate: track (party_id, role) combinations to avoid unique constraint violation
        seen_party_roles: set[tuple[str, str, str]] = set()  # (name, org, role)

        for party_domain in domain.responsible_parties:
            role_value = party_domain.role.value if isinstance(party_domain.role, ResponsiblePartyRole) else party_domain.role

            # Create dedup key
            dedup_key = (
                party_domain.name or "",
                party_domain.organisation or "",
                role_value or "",
            )

            if dedup_key in seen_party_roles:
                continue  # Skip duplicate
            seen_party_roles.add(dedup_key)

            # Find or create the party
            party = _find_or_create_party(session, party_domain)

            # Create the association with role
            association = DatasetResponsibleParty(
                party=party,
                role=role_value,
            )
            dataset.party_associations.append(association)

    # Handle distributions (1:N)
    for dist_domain in domain.distributions:
        distribution = Distribution(
            url=dist_domain.url,
            name=dist_domain.name,
            format=dist_domain.format,
            access_type=dist_domain.access_type.value if isinstance(dist_domain.access_type, AccessType) else dist_domain.access_type,
            size_bytes=dist_domain.size_bytes,
            description=dist_domain.description,
        )
        dataset.distributions.append(distribution)

    # Handle related documents (1:N)
    for rel_domain in domain.related_documents:
        rel_type = rel_domain.relationship_type.value if isinstance(rel_domain.relationship_type, RelationshipType) else rel_domain.relationship_type
        related = RelatedDocument(
            target_identifier=rel_domain.identifier,
            relationship_type=rel_type,
            title=rel_domain.title,
            url=rel_domain.url,
        )
        dataset.related_documents.append(related)

    # Handle supporting documents (1:N)
    for supp_domain in domain.supporting_documents:
        supporting = SupportingDocument(
            filename=supp_domain.filename,
            url=supp_domain.url,
            content_type=supp_domain.content_type,
            size_bytes=supp_domain.size_bytes,
            description=supp_domain.description,
            extracted_text=supp_domain.extracted_text,
        )
        dataset.supporting_documents.append(supporting)

    # Store raw document if provided
    if include_raw and domain.raw_document and domain.source_format:
        raw_doc = RawDocument(
            format_type=domain.source_format,
            content=domain.raw_document,
        )
        dataset.raw_documents.append(raw_doc)

    return dataset

def _find_or_create_party(
    session: Session,
    party_domain: DomainResponsibleParty,
) -> ResponsibleParty:
    """
    Find existing party or create new one.

    Matches on name + organisation combination.
    Uses merge to handle duplicates gracefully.
    """
    # First check in session's identity map (already loaded objects)
    for obj in session.new:
        if isinstance(obj, ResponsibleParty):
            if obj.name == party_domain.name and obj.organisation == party_domain.organisation:
                return obj

    # Then check database
    party = session.query(ResponsibleParty).filter_by(
        name=party_domain.name,
        organisation=party_domain.organisation,
    ).first()

    if not party:
        party = ResponsibleParty(
            name=party_domain.name,
            organisation=party_domain.organisation,
            email=party_domain.email,
            orcid=party_domain.orcid,
        )
        session.add(party)

    return party

# =============================================================================
# ORM -> Domain Converters
# =============================================================================

def orm_to_domain(dataset: Dataset) -> DatasetMetadata:
    """
    Convert a SQLAlchemy Dataset to Pydantic DatasetMetadata.

    Args:
        dataset: SQLAlchemy Dataset instance

    Returns:
        Pydantic DatasetMetadata instance
    """
    # Parse topic categories from JSON
    topic_categories = []
    if dataset.topic_categories:
        try:
            tc_list = json.loads(dataset.topic_categories)
            for tc in tc_list:
                try:
                    topic_categories.append(TopicCategory(tc))
                except ValueError:
                    pass  # Skip invalid categories
        except json.JSONDecodeError:
            pass

    # Build bounding box if present
    bounding_box = None
    if all(v is not None for v in [dataset.bbox_west, dataset.bbox_east,
                                    dataset.bbox_south, dataset.bbox_north]):
        bounding_box = BoundingBox(
            west=dataset.bbox_west,
            east=dataset.bbox_east,
            south=dataset.bbox_south,
            north=dataset.bbox_north,
        )

    # Build temporal extent if present
    temporal_extent = None
    if dataset.temporal_start is not None or dataset.temporal_end is not None:
        temporal_extent = TemporalExtent(
            start_date=dataset.temporal_start,
            end_date=dataset.temporal_end,
        )

    # Convert keywords
    keywords = [kw.keyword for kw in dataset.keywords]

    # Convert responsible parties with roles
    responsible_parties = []
    for assoc in dataset.party_associations:
        party = assoc.party
        responsible_parties.append(DomainResponsibleParty(
            name=party.name,
            organisation=party.organisation,
            email=party.email,
            orcid=party.orcid,
            role=assoc.role,
        ))

    # Convert distributions
    distributions = [
        DistributionInfo(
            url=dist.url,
            name=dist.name,
            format=dist.format,
            access_type=dist.access_type,
            size_bytes=dist.size_bytes,
            description=dist.description,
        )
        for dist in dataset.distributions
    ]

    # Convert related documents
    related_documents = [
        DomainRelatedDocument(
            identifier=rel.target_identifier,
            relationship_type=rel.relationship_type,
            title=rel.title,
            url=rel.url,
        )
        for rel in dataset.related_documents
    ]

    # Convert supporting documents
    supporting_documents = [
        DomainSupportingDocument(
            filename=supp.filename,
            url=supp.url,
            content_type=supp.content_type,
            size_bytes=supp.size_bytes,
            description=supp.description,
            extracted_text=supp.extracted_text,
        )
        for supp in dataset.supporting_documents
    ]

    # Get raw document if available (prefer JSON format)
    raw_document = None
    source_format = None
    for raw in dataset.raw_documents:
        if raw.format_type == 'json':
            raw_document = raw.content
            source_format = raw.format_type
            break
    if raw_document is None and dataset.raw_documents:
        raw_doc = dataset.raw_documents[0]
        raw_document = raw_doc.content
        source_format = raw_doc.format_type

    return DatasetMetadata(
        identifier=dataset.identifier,
        title=dataset.title,
        abstract=dataset.abstract,
        lineage=dataset.lineage,
        topic_categories=topic_categories,
        keywords=keywords,
        bounding_box=bounding_box,
        temporal_extent=temporal_extent,
        responsible_parties=responsible_parties,
        distributions=distributions,
        related_documents=related_documents,
        supporting_documents=supporting_documents,
        raw_document=raw_document,
        source_format=source_format,
    )


# =============================================================================
# Utility Functions
# =============================================================================

def update_dataset_from_domain(
    existing: Dataset,
    domain: DatasetMetadata,
    session: Session,
) -> Dataset:
    """
    Update an existing Dataset record from a domain model.

    Handles clearing and re-creating relationships.

    Args:
        existing: Existing SQLAlchemy Dataset
        domain: Updated Pydantic domain model
        session: SQLAlchemy session

    Returns:
        Updated Dataset instance
    """
    # Update scalar fields
    existing.title = domain.title
    existing.abstract = domain.abstract
    existing.lineage = domain.lineage
    existing.topic_categories = json.dumps([tc.value if isinstance(tc, TopicCategory) else tc
                                            for tc in domain.topic_categories]) if domain.topic_categories else None

    # Update bounding box
    if domain.bounding_box:
        existing.bbox_west = domain.bounding_box.west
        existing.bbox_east = domain.bounding_box.east
        existing.bbox_south = domain.bounding_box.south
        existing.bbox_north = domain.bounding_box.north
    else:
        existing.bbox_west = None
        existing.bbox_east = None
        existing.bbox_south = None
        existing.bbox_north = None

    # Update temporal extent
    if domain.temporal_extent:
        existing.temporal_start = domain.temporal_extent.start_date
        existing.temporal_end = domain.temporal_extent.end_date
    else:
        existing.temporal_start = None
        existing.temporal_end = None

    # Clear and rebuild relationships
    existing.keywords.clear()
    existing.party_associations.clear()
    existing.distributions.clear()
    existing.related_documents.clear()
    existing.supporting_documents.clear()

    # Use no_autoflush to prevent premature flush during lookups
    with session.no_autoflush:
        # Re-add keywords
        for kw_text in domain.keywords:
            # Check session's pending objects first
            keyword = None
            for obj in session.new:
                if isinstance(obj, Keyword) and obj.keyword == kw_text:
                    keyword = obj
                    break

            if not keyword:
                keyword = session.query(Keyword).filter_by(keyword=kw_text).first()

            if not keyword:
                keyword = Keyword(keyword=kw_text)
                session.add(keyword)

            dataset.keywords.append(keyword)
        # Re-add responsible parties (with deduplication)
        seen_party_roles: set[tuple[str, str, str]] = set()

        for party_domain in domain.responsible_parties:
            role_value = party_domain.role.value if isinstance(party_domain.role, ResponsiblePartyRole) else party_domain.role

            dedup_key = (
                party_domain.name or "",
                party_domain.organisation or "",
                role_value or "",
            )

            if dedup_key in seen_party_roles:
                continue
            seen_party_roles.add(dedup_key)

            party = _find_or_create_party(session, party_domain)
            association = DatasetResponsibleParty(
                party=party,
                role=role_value,
            )
            existing.party_associations.append(association)

    # Re-add distributions
    for dist_domain in domain.distributions:
        distribution = Distribution(
            url=dist_domain.url,
            name=dist_domain.name,
            format=dist_domain.format,
            access_type=dist_domain.access_type.value if isinstance(dist_domain.access_type, AccessType) else dist_domain.access_type,
            size_bytes=dist_domain.size_bytes,
            description=dist_domain.description,
        )
        existing.distributions.append(distribution)

    # Re-add related documents
    for rel_domain in domain.related_documents:
        rel_type = rel_domain.relationship_type.value if isinstance(rel_domain.relationship_type, RelationshipType) else rel_domain.relationship_type
        related = RelatedDocument(
            target_identifier=rel_domain.identifier,
            relationship_type=rel_type,
            title=rel_domain.title,
            url=rel_domain.url,
        )
        existing.related_documents.append(related)

    # Re-add supporting documents
    for supp_domain in domain.supporting_documents:
        supporting = SupportingDocument(
            filename=supp_domain.filename,
            url=supp_domain.url,
            content_type=supp_domain.content_type,
            size_bytes=supp_domain.size_bytes,
            description=supp_domain.description,
            extracted_text=supp_domain.extracted_text,
        )
        existing.supporting_documents.append(supporting)

    return existing