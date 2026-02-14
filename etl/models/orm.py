"""
SQLAlchemy ORM models for database persistence.

These models define the database schema and handle persistence.
They are separate from the Pydantic domain models to maintain
separation between domain logic and persistence concerns.

Usage:
    from etl.models.orm import Dataset, Keyword, Base
    from sqlalchemy import create_engine

    engine = create_engine("sqlite:///data/metadata.db")
    Base.metadata.create_all(engine)
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# =============================================================================
# Base Class
# =============================================================================

class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


# =============================================================================
# Association Tables (Many-to-Many)
# =============================================================================

class DatasetKeyword(Base):
    """
    Association table for Dataset <-> Keyword many-to-many relationship.
    """
    __tablename__ = "dataset_keywords"

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    keyword_id: Mapped[int] = mapped_column(
        ForeignKey("keywords.id", ondelete="CASCADE"),
        primary_key=True,
    )


class DatasetResponsibleParty(Base):
    """
    Association table for Dataset <-> ResponsibleParty relationship.

    Includes the role since a party can have different roles
    on different datasets (e.g., author on one, publisher on another).
    """
    __tablename__ = "dataset_responsible_parties"

    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        primary_key=True,
    )
    party_id: Mapped[int] = mapped_column(
        ForeignKey("responsible_parties.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Relationships
    dataset: Mapped["Dataset"] = relationship(back_populates="party_associations")
    party: Mapped["ResponsibleParty"] = relationship(back_populates="dataset_associations")


# =============================================================================
# Main Tables
# =============================================================================

class Dataset(Base):
    """
    Main dataset table.

    Contains core metadata fields and embeds 1:1 relationships
    (bounding box, temporal extent) directly in the table.
    """
    __tablename__ = "datasets"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Core identification
    identifier: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="CEH dataset UUID",
    )
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
    )
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    lineage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Topic categories stored as JSON string (from fixed enum, simple approach)
    topic_categories: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="JSON array of topic category codes",
    )

    # Embedded BoundingBox (1:1)
    bbox_west: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_east: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_south: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bbox_north: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Embedded TemporalExtent (1:1)
    temporal_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    temporal_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships (1:N)
    distributions: Mapped[list["Distribution"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    related_documents: Mapped[list["RelatedDocument"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    supporting_documents: Mapped[list["SupportingDocument"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    raw_documents: Mapped[list["RawDocument"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Relationships (M:N)
    keywords: Mapped[list["Keyword"]] = relationship(
        secondary="dataset_keywords",
        back_populates="datasets",
        lazy="selectin",
    )
    party_associations: Mapped[list["DatasetResponsibleParty"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Dataset(id={self.id}, identifier='{self.identifier}', title='{self.title[:50]}...')>"


class Keyword(Base):
    """
    Keyword/tag for dataset discovery.

    Normalized to allow efficient searching and avoid duplication.
    Many-to-many relationship with datasets.
    """
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # Relationship
    datasets: Mapped[list["Dataset"]] = relationship(
        secondary="dataset_keywords",
        back_populates="keywords",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Keyword(id={self.id}, keyword='{self.keyword}')>"


class ResponsibleParty(Base):
    """
    Person or organisation responsible for datasets.

    Normalized to avoid duplication when same party appears
    on multiple datasets.
    """
    __tablename__ = "responsible_parties"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    organisation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    orcid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationship
    dataset_associations: Mapped[list["DatasetResponsibleParty"]] = relationship(
        back_populates="party",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Unique constraint on name + organisation combination
    __table_args__ = (
        UniqueConstraint('name', 'organisation', name='uq_party_identity'),
    )

    def __repr__(self) -> str:
        identity = self.name or self.organisation
        return f"<ResponsibleParty(id={self.id}, identity='{identity}')>"


class Distribution(Base):
    """
    Distribution/download option for a dataset.

    One-to-many relationship with Dataset.
    """
    __tablename__ = "distributions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    access_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    dataset: Mapped["Dataset"] = relationship(back_populates="distributions")

    def __repr__(self) -> str:
        return f"<Distribution(id={self.id}, url='{self.url[:50]}...')>"


class RelatedDocument(Base):
    """
    Reference to a related dataset or document.

    One-to-many relationship with Dataset.
    """
    __tablename__ = "related_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    target_identifier: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Identifier or URL of related document",
    )
    relationship_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="other",
    )
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    dataset: Mapped["Dataset"] = relationship(back_populates="related_documents")

    def __repr__(self) -> str:
        return f"<RelatedDocument(id={self.id}, target='{self.target_identifier}')>"


class SupportingDocument(Base):
    """
    Supporting documentation file (PDF, doc, etc.).

    One-to-many relationship with Dataset.
    Includes extracted_text for RAG/embedding purposes.
    """
    __tablename__ = "supporting_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Local path to downloaded file",
    )
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Text extracted from document for RAG",
    )

    # Relationship
    dataset: Mapped["Dataset"] = relationship(back_populates="supporting_documents")

    def __repr__(self) -> str:
        return f"<SupportingDocument(id={self.id}, filename='{self.filename}')>"


class RawDocument(Base):
    """
    Raw metadata document storage.

    Stores original XML, JSON, JSON-LD, or RDF document
    for reference and potential re-parsing.
    """
    __tablename__ = "raw_documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    format_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Format: iso19115, json, jsonld, rdf",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    # Relationship
    dataset: Mapped["Dataset"] = relationship(back_populates="raw_documents")

    # Unique constraint: one document per format per dataset
    __table_args__ = (
        UniqueConstraint('dataset_id', 'format_type', name='uq_dataset_format'),
        Index('idx_raw_doc_format', 'format_type'),
    )

    def __repr__(self) -> str:
        return f"<RawDocument(id={self.id}, format='{self.format_type}')>"


# =============================================================================
# Embedding Tracking Table
# =============================================================================

class EmbeddingRecord(Base):
    """
    Tracks what has been embedded in the vector store.

    Used to synchronize SQLite and vector store, and to
    avoid re-embedding unchanged content.
    """
    __tablename__ = "embedding_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: dataset, supporting_document",
    )
    source_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="ID in source table",
    )
    embedding_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type: title_abstract, full_text",
    )
    vector_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="ID in vector store",
    )
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Hash of embedded content for change detection",
    )
    embedded_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint('source_type', 'source_id', 'embedding_type', name='uq_embedding'),
        Index('idx_embedding_source', 'source_type', 'source_id'),
    )

    def __repr__(self) -> str:
        return f"<EmbeddingRecord(source={self.source_type}:{self.source_id}, type='{self.embedding_type}')>"

class User(Base):
    """User account."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255))
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime)
    preferences = Column(Text)  # JSON string

    # Relationships
    search_history = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    favourites = relationship("UserFavourite", back_populates="user", cascade="all, delete-orphan")


class SearchHistory(Base):
    """Search history record."""
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # Nullable for anonymous
    query_text = Column(String(500), nullable=False)
    search_type = Column(String(50), default="semantic")
    result_count = Column(Integer, default=0)
    searched_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    duration_ms = Column(Integer)

    # Relationships
    user = relationship("User", back_populates="search_history")


class UserFavourite(Base):
    """User's favourite datasets."""
    __tablename__ = "user_favourites"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("User", back_populates="favourites")
    dataset = relationship("Dataset")

    __table_args__ = (
        # Unique constraint: user can only favourite a dataset once
        {"sqlite_autoincrement": True},
    )

# =============================================================================
# Database Utilities
# =============================================================================

def create_database(db_path: str) -> None:
    """
    Create database with all tables.

    Args:
        db_path: Path to SQLite database file.
    """
    engine = create_engine(f"sqlite:///{db_path}")

    # Enable foreign keys for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def get_engine(db_path: str):
    """
    Get SQLAlchemy engine with SQLite pragmas configured.

    Args:
        db_path: Path to SQLite database file.

    Returns:
        SQLAlchemy Engine instance.
    """
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,  # Set True for SQL debugging
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
        cursor.close()

    return engine