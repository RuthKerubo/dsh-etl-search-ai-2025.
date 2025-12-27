"""
Tests for ORM models and database creation.
"""
import pytest
import tempfile
from pathlib import Path

from etl.models import (
    # Domain
    DatasetMetadata,
    BoundingBox,
    TemporalExtent,
    ResponsibleParty,
    DistributionInfo,
    # ORM
    Base,
    Dataset,
    create_database,
    get_engine,
    # Converters
    domain_to_orm,
    orm_to_domain,
)
from sqlalchemy.orm import Session
from datetime import date


class TestDatabaseCreation:
    """Tests for database setup."""
    
    def test_create_database(self, tmp_path):
        """Test creating database with all tables."""
        db_path = tmp_path / "test.db"
        engine = create_database(str(db_path))
        
        assert db_path.exists()
        
        # Check tables were created
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        assert "datasets" in tables
        assert "keywords" in tables
        assert "responsible_parties" in tables
        assert "distributions" in tables
        assert "dataset_keywords" in tables
        assert "dataset_responsible_parties" in tables


class TestConverters:
    """Tests for domain <-> ORM conversion."""
    
    def test_domain_to_orm_minimal(self, tmp_path):
        """Test converting minimal domain model to ORM."""
        db_path = tmp_path / "test.db"
        engine = create_database(str(db_path))
        
        domain = DatasetMetadata(
            identifier="test-123",
            title="Test Dataset",
            abstract="Test abstract",
        )
        
        with Session(engine) as session:
            orm_obj = domain_to_orm(domain, session)
            session.add(orm_obj)
            session.commit()
            
            # Verify it was saved
            saved = session.query(Dataset).filter_by(identifier="test-123").first()
            assert saved is not None
            assert saved.title == "Test Dataset"
    
    def test_domain_to_orm_with_relationships(self, tmp_path):
        """Test converting domain model with relationships."""
        db_path = tmp_path / "test.db"
        engine = create_database(str(db_path))
        
        domain = DatasetMetadata(
            identifier="test-456",
            title="Full Dataset",
            abstract="Description",
            keywords=["water", "quality"],
            bounding_box=BoundingBox(west=-8, east=2, south=50, north=60),
            temporal_extent=TemporalExtent(start_date=date(2020, 1, 1)),
            responsible_parties=[
                ResponsibleParty(organisation="UKCEH", role="publisher"),
            ],
            distributions=[
                DistributionInfo(url="https://example.com/data.zip", access_type="download"),
            ],
        )
        
        with Session(engine) as session:
            orm_obj = domain_to_orm(domain, session)
            session.add(orm_obj)
            session.commit()
            
            # Verify relationships
            saved = session.query(Dataset).filter_by(identifier="test-456").first()
            assert len(saved.keywords) == 2
            assert len(saved.party_associations) == 1
            assert len(saved.distributions) == 1
            assert saved.bbox_west == -8
    
    def test_orm_to_domain_roundtrip(self, tmp_path):
        """Test converting ORM back to domain model."""
        db_path = tmp_path / "test.db"
        engine = create_database(str(db_path))
        
        original = DatasetMetadata(
            identifier="roundtrip-789",
            title="Roundtrip Test",
            abstract="Testing roundtrip conversion",
            keywords=["test", "roundtrip"],
        )
        
        with Session(engine) as session:
            # Domain -> ORM -> Save
            orm_obj = domain_to_orm(original, session)
            session.add(orm_obj)
            session.commit()
            
            # Reload and convert back
            saved = session.query(Dataset).filter_by(identifier="roundtrip-789").first()
            restored = orm_to_domain(saved)
            
            assert restored.identifier == original.identifier
            assert restored.title == original.title
            assert restored.abstract == original.abstract
            assert set(restored.keywords) == set(original.keywords)