"""
Tests for domain models.

Run with: pytest tests/test_models.py -v
"""

import pytest
from datetime import date

from etl.models import (
    AccessType,
    BoundingBox,
    DatasetMetadata,
    DistributionInfo,
    RelatedDocument,
    RelationshipType,
    ResponsibleParty,
    ResponsiblePartyRole,
    SupportingDocument,
    TemporalExtent,
    TopicCategory,
    create_minimal_dataset,
)


# =============================================================================
# BoundingBox Tests
# =============================================================================

class TestBoundingBox:
    """Tests for BoundingBox model."""
    
    def test_valid_bounding_box(self):
        """Test creating a valid bounding box."""
        bbox = BoundingBox(
            west=-8.6,
            east=1.8,
            south=49.9,
            north=60.8,
        )
        assert bbox.west == -8.6
        assert bbox.east == 1.8
        assert bbox.south == 49.9
        assert bbox.north == 60.8
    
    def test_invalid_latitude_too_high(self):
        """Test that latitude > 90 raises error."""
        with pytest.raises(ValueError):
            BoundingBox(west=0, east=1, south=0, north=91)
    
    def test_invalid_latitude_too_low(self):
        """Test that latitude < -90 raises error."""
        with pytest.raises(ValueError):
            BoundingBox(west=0, east=1, south=-91, north=0)
    
    def test_invalid_longitude_too_high(self):
        """Test that longitude > 180 raises error."""
        with pytest.raises(ValueError):
            BoundingBox(west=181, east=0, south=0, north=1)
    
    def test_invalid_longitude_too_low(self):
        """Test that longitude < -180 raises error."""
        with pytest.raises(ValueError):
            BoundingBox(west=-181, east=0, south=0, north=1)
    
    def test_north_less_than_south_raises_error(self):
        """Test that north < south raises error."""
        with pytest.raises(ValueError, match="North.*must be >= south"):
            BoundingBox(west=0, east=1, south=50, north=40)
    
    def test_center_calculation(self):
        """Test center point calculation."""
        bbox = BoundingBox(west=-10, east=10, south=40, north=60)
        center = bbox.center
        assert center == (0.0, 50.0)
    
    def test_serialization(self):
        """Test dict serialization."""
        bbox = BoundingBox(west=-8.6, east=1.8, south=49.9, north=60.8)
        data = bbox.model_dump()
        assert data == {
            "west": -8.6,
            "east": 1.8,
            "south": 49.9,
            "north": 60.8,
        }


# =============================================================================
# TemporalExtent Tests
# =============================================================================

class TestTemporalExtent:
    """Tests for TemporalExtent model."""
    
    def test_valid_date_range(self):
        """Test creating a valid temporal extent."""
        extent = TemporalExtent(
            start_date=date(2020, 1, 1),
            end_date=date(2023, 12, 31),
        )
        assert extent.start_date == date(2020, 1, 1)
        assert extent.end_date == date(2023, 12, 31)
    
    def test_open_ended_no_end_date(self):
        """Test ongoing data collection (no end date)."""
        extent = TemporalExtent(start_date=date(2020, 1, 1))
        assert extent.is_ongoing is True
        assert extent.is_open_ended is True
    
    def test_open_ended_no_start_date(self):
        """Test unknown start date."""
        extent = TemporalExtent(end_date=date(2023, 12, 31))
        assert extent.is_open_ended is True
        assert extent.is_ongoing is False
    
    def test_parse_string_date(self):
        """Test parsing date from string."""
        extent = TemporalExtent(
            start_date="2020-01-01",
            end_date="2023-12-31",
        )
        assert extent.start_date == date(2020, 1, 1)
        assert extent.end_date == date(2023, 12, 31)
    
    def test_parse_year_only(self):
        """Test parsing year-only date."""
        extent = TemporalExtent(start_date="2020")
        assert extent.start_date == date(2020, 1, 1)
    
    def test_end_before_start_raises_error(self):
        """Test that end before start raises error."""
        with pytest.raises(ValueError, match="end_date.*must be >= start_date"):
            TemporalExtent(
                start_date=date(2023, 1, 1),
                end_date=date(2020, 1, 1),
            )
    
    def test_empty_string_becomes_none(self):
        """Test that empty string is treated as None."""
        extent = TemporalExtent(start_date="", end_date="")
        assert extent.start_date is None
        assert extent.end_date is None


# =============================================================================
# ResponsibleParty Tests
# =============================================================================

class TestResponsibleParty:
    """Tests for ResponsibleParty model."""
    
    def test_valid_person(self):
        """Test creating a valid responsible party."""
        party = ResponsibleParty(
            name="John Smith",
            organisation="UKCEH",
            role="publisher",
            email="john@ceh.ac.uk",
        )
        assert party.name == "John Smith"
        assert party.role == ResponsiblePartyRole.PUBLISHER
    
    def test_organisation_only(self):
        """Test party with only organisation."""
        party = ResponsibleParty(
            organisation="UKCEH",
            role="publisher",
        )
        assert party.organisation == "UKCEH"
        assert party.name is None
    
    def test_no_name_or_org_raises_error(self):
        """Test that party without name or org raises error."""
        with pytest.raises(ValueError, match="Either name or organisation"):
            ResponsibleParty(role="publisher")
    
    def test_role_parsing_case_insensitive(self):
        """Test that role parsing is case-insensitive."""
        party = ResponsibleParty(name="Test", role="Publisher")
        assert party.role == ResponsiblePartyRole.PUBLISHER
        
        party2 = ResponsibleParty(name="Test", role="POINT_OF_CONTACT")
        assert party2.role == ResponsiblePartyRole.POINT_OF_CONTACT
    
    def test_unknown_role_becomes_other(self):
        """Test that unknown role defaults to OTHER."""
        party = ResponsibleParty(name="Test", role="unknown_role")
        assert party.role == ResponsiblePartyRole.OTHER
    
    def test_display_name(self):
        """Test display name generation."""
        party = ResponsibleParty(name="John", organisation="UKCEH")
        assert party.display_name == "John (UKCEH)"
        
        party2 = ResponsibleParty(organisation="UKCEH")
        assert party2.display_name == "UKCEH"
    
    def test_invalid_email_becomes_none(self):
        """Test that invalid email is treated as None."""
        party = ResponsibleParty(name="Test", email="not-an-email")
        assert party.email is None


# =============================================================================
# DistributionInfo Tests
# =============================================================================

class TestDistributionInfo:
    """Tests for DistributionInfo model."""
    
    def test_valid_distribution(self):
        """Test creating a valid distribution."""
        dist = DistributionInfo(
            url="https://example.com/download.zip",
            format="application/zip",
            access_type="download",
            size_bytes=1024,
        )
        assert dist.url == "https://example.com/download.zip"
        assert dist.access_type == AccessType.DOWNLOAD
    
    def test_url_required(self):
        """Test that URL is required."""
        with pytest.raises(ValueError):
            DistributionInfo(format="zip")
    
    def test_access_type_parsing(self):
        """Test access type parsing."""
        dist = DistributionInfo(url="http://test.com", access_type="fileAccess")
        assert dist.access_type == AccessType.FILE_ACCESS
    
    def test_negative_size_raises_error(self):
        """Test that negative size raises error."""
        with pytest.raises(ValueError):
            DistributionInfo(url="http://test.com", size_bytes=-1)


# =============================================================================
# DatasetMetadata Tests
# =============================================================================

class TestDatasetMetadata:
    """Tests for DatasetMetadata model."""
    
    def test_minimal_dataset(self):
        """Test creating minimal dataset with required fields only."""
        dataset = DatasetMetadata(
            identifier="abc123",
            title="Test Dataset",
        )
        assert dataset.identifier == "abc123"
        assert dataset.title == "Test Dataset"
        assert dataset.keywords == []
        assert dataset.distributions == []
    
    def test_full_dataset(self):
        """Test creating a fully populated dataset."""
        dataset = DatasetMetadata(
            identifier="abc123",
            title="UK River Water Quality",
            abstract="Water quality measurements from UK rivers.",
            keywords=["water", "quality", "rivers"],
            topic_categories=["inlandWaters", "environment"],
            bounding_box=BoundingBox(west=-8, east=2, south=50, north=60),
            temporal_extent=TemporalExtent(
                start_date=date(2020, 1, 1),
                end_date=date(2023, 12, 31),
            ),
            responsible_parties=[
                ResponsibleParty(organisation="UKCEH", role="publisher"),
            ],
            distributions=[
                DistributionInfo(url="https://example.com/data.zip"),
            ],
        )
        assert len(dataset.keywords) == 3
        assert dataset.has_spatial_extent is True
        assert dataset.has_temporal_extent is True
        assert dataset.has_downloads is False  # No download access_type set
    
    def test_keyword_deduplication(self):
        """Test that duplicate keywords are removed."""
        dataset = DatasetMetadata(
            identifier="abc",
            title="Test",
            keywords=["water", "water", "rivers", "water"],
        )
        assert dataset.keywords == ["water", "rivers"]
    
    def test_keyword_from_comma_string(self):
        """Test parsing keywords from comma-separated string."""
        dataset = DatasetMetadata(
            identifier="abc",
            title="Test",
            keywords="water, quality, rivers",
        )
        assert dataset.keywords == ["water", "quality", "rivers"]
    
    def test_search_text_property(self):
        """Test search text generation for embedding."""
        dataset = DatasetMetadata(
            identifier="abc",
            title="River Data",
            abstract="Water quality measurements.",
            keywords=["water", "rivers"],
        )
        search_text = dataset.search_text
        assert "River Data" in search_text
        assert "Water quality measurements" in search_text
        assert "water" in search_text
    
    def test_to_dict_excludes_raw_document(self):
        """Test that to_dict excludes raw_document by default."""
        dataset = DatasetMetadata(
            identifier="abc",
            title="Test",
            raw_document="<xml>...</xml>",
        )
        data = dataset.to_dict(include_raw=False)
        assert "raw_document" not in data
    
    def test_to_dict_includes_raw_document_when_requested(self):
        """Test that to_dict includes raw_document when requested."""
        dataset = DatasetMetadata(
            identifier="abc",
            title="Test",
            raw_document="<xml>...</xml>",
        )
        data = dataset.to_dict(include_raw=True)
        assert "raw_document" in data
    
    def test_from_dict(self):
        """Test creating dataset from dict."""
        data = {
            "identifier": "abc123",
            "title": "Test Dataset",
            "abstract": "Test abstract",
            "keywords": ["test", "data"],
        }
        dataset = DatasetMetadata.from_dict(data)
        assert dataset.identifier == "abc123"
        assert dataset.title == "Test Dataset"
    
    def test_publisher_property(self):
        """Test getting publisher from responsible parties."""
        dataset = DatasetMetadata(
            identifier="abc",
            title="Test",
            responsible_parties=[
                ResponsibleParty(name="Author", role="author"),
                ResponsibleParty(organisation="UKCEH", role="publisher"),
            ],
        )
        publisher = dataset.publisher
        assert publisher is not None
        assert publisher.organisation == "UKCEH"


# =============================================================================
# Factory Function Tests
# =============================================================================

class TestFactoryFunctions:
    """Tests for factory functions."""
    
    def test_create_minimal_dataset(self):
        """Test creating minimal dataset via factory."""
        dataset = create_minimal_dataset(
            identifier="abc123",
            title="Test Dataset",
            abstract="Test abstract",
        )
        assert dataset.identifier == "abc123"
        assert dataset.title == "Test Dataset"
        assert dataset.abstract == "Test abstract"


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSerialization:
    """Tests for model serialization/deserialization."""
    
    def test_full_roundtrip(self):
        """Test full serialization roundtrip."""
        original = DatasetMetadata(
            identifier="abc123",
            title="Test Dataset",
            abstract="Description",
            keywords=["water", "quality"],
            bounding_box=BoundingBox(west=-8, east=2, south=50, north=60),
            temporal_extent=TemporalExtent(
                start_date=date(2020, 1, 1),
            ),
            responsible_parties=[
                ResponsibleParty(organisation="UKCEH", role="publisher"),
            ],
            distributions=[
                DistributionInfo(
                    url="https://example.com/data.zip",
                    access_type="download",
                ),
            ],
        )
        
        # Serialize to dict
        data = original.to_dict()
        
        # Deserialize back
        restored = DatasetMetadata.from_dict(data)
        
        # Compare
        assert restored.identifier == original.identifier
        assert restored.title == original.title
        assert restored.bounding_box.north == original.bounding_box.north
        assert restored.temporal_extent.start_date == original.temporal_extent.start_date
        assert len(restored.responsible_parties) == 1
        assert len(restored.distributions) == 1