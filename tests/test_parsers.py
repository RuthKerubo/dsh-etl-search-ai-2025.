"""
Tests for metadata parsers.
"""
import pytest
from datetime import date

from etl.parsers import (
    CEHJSONParser,
    ISO19115Parser,
    ParserRegistry,
    ParseError,
)
from etl.models import DatasetMetadata


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_ceh_json():
    """Sample CEH JSON response."""
    return '''{
        "id": "f710bed1-e564-47bf-b82c-4c2a2fe2810e",
        "title": "UK River Water Quality Dataset",
        "description": "Water quality measurements from UK rivers.",
        "lineage": "Data collected from monitoring stations.",
        "boundingBoxes": [{
            "westBoundLongitude": -8.648,
            "eastBoundLongitude": 1.768,
            "southBoundLatitude": 49.864,
            "northBoundLatitude": 60.861
        }],
        "temporalExtents": [{
            "begin": "2020-01-01",
            "end": "2023-12-31"
        }],
        "topicCategories": [{"value": "inlandWaters"}, {"value": "environment"}],
        "keywordsOther": [{"value": "water"}, {"value": "quality"}],
        "keywordsPlace": [{"value": "United Kingdom"}],
        "responsibleParties": [{
            "givenName": "John",
            "familyName": "Smith",
            "organisationName": "UKCEH",
            "role": "author",
            "email": "john.smith@ceh.ac.uk"
        }, {
            "organisationName": "UKCEH",
            "role": "publisher"
        }],
        "onlineResources": [{
            "url": "https://example.com/download.zip",
            "name": "Download data",
            "function": "download"
        }],
        "relationships": [{
            "target": "parent-dataset-uuid",
            "relation": "https://vocabs.ceh.ac.uk/eidc#memberOf"
        }],
        "infoLinks": [{
            "url": "https://example.com/docs.zip",
            "name": "Supporting documentation"
        }]
    }'''


@pytest.fixture
def sample_iso19115_xml():
    """Sample ISO 19115 XML response."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco"
                 xmlns:gml="http://www.opengis.net/gml/3.2">
    <gmd:fileIdentifier>
        <gco:CharacterString>f710bed1-e564-47bf-b82c-4c2a2fe2810e</gco:CharacterString>
    </gmd:fileIdentifier>
    <gmd:identificationInfo>
        <gmd:MD_DataIdentification>
            <gmd:citation>
                <gmd:CI_Citation>
                    <gmd:title>
                        <gco:CharacterString>UK River Water Quality Dataset</gco:CharacterString>
                    </gmd:title>
                </gmd:CI_Citation>
            </gmd:citation>
            <gmd:abstract>
                <gco:CharacterString>Water quality measurements from UK rivers.</gco:CharacterString>
            </gmd:abstract>
            <gmd:topicCategory>
                <gmd:MD_TopicCategoryCode>inlandWaters</gmd:MD_TopicCategoryCode>
            </gmd:topicCategory>
            <gmd:descriptiveKeywords>
                <gmd:MD_Keywords>
                    <gmd:keyword>
                        <gco:CharacterString>water</gco:CharacterString>
                    </gmd:keyword>
                    <gmd:keyword>
                        <gco:CharacterString>quality</gco:CharacterString>
                    </gmd:keyword>
                </gmd:MD_Keywords>
            </gmd:descriptiveKeywords>
            <gmd:extent>
                <gmd:EX_Extent>
                    <gmd:geographicElement>
                        <gmd:EX_GeographicBoundingBox>
                            <gmd:westBoundLongitude>
                                <gco:Decimal>-8.648</gco:Decimal>
                            </gmd:westBoundLongitude>
                            <gmd:eastBoundLongitude>
                                <gco:Decimal>1.768</gco:Decimal>
                            </gmd:eastBoundLongitude>
                            <gmd:southBoundLatitude>
                                <gco:Decimal>49.864</gco:Decimal>
                            </gmd:southBoundLatitude>
                            <gmd:northBoundLatitude>
                                <gco:Decimal>60.861</gco:Decimal>
                            </gmd:northBoundLatitude>
                        </gmd:EX_GeographicBoundingBox>
                    </gmd:geographicElement>
                    <gmd:temporalElement>
                        <gmd:EX_TemporalExtent>
                            <gmd:extent>
                                <gml:TimePeriod>
                                    <gml:beginPosition>2020-01-01</gml:beginPosition>
                                    <gml:endPosition>2023-12-31</gml:endPosition>
                                </gml:TimePeriod>
                            </gmd:extent>
                        </gmd:EX_TemporalExtent>
                    </gmd:temporalElement>
                </gmd:EX_Extent>
            </gmd:extent>
            <gmd:pointOfContact>
                <gmd:CI_ResponsibleParty>
                    <gmd:individualName>
                        <gco:CharacterString>John Smith</gco:CharacterString>
                    </gmd:individualName>
                    <gmd:organisationName>
                        <gco:CharacterString>UKCEH</gco:CharacterString>
                    </gmd:organisationName>
                    <gmd:role>
                        <gmd:CI_RoleCode codeListValue="author"/>
                    </gmd:role>
                </gmd:CI_ResponsibleParty>
            </gmd:pointOfContact>
        </gmd:MD_DataIdentification>
    </gmd:identificationInfo>
</gmd:MD_Metadata>'''


# =============================================================================
# CEH JSON Parser Tests
# =============================================================================

class TestCEHJSONParser:
    """Tests for CEH JSON parser."""
    
    def test_parse_complete_json(self, sample_ceh_json):
        """Test parsing complete JSON response."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert metadata.identifier == "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
        assert metadata.title == "UK River Water Quality Dataset"
        assert metadata.abstract == "Water quality measurements from UK rivers."
        assert metadata.lineage == "Data collected from monitoring stations."
    
    def test_parse_bounding_box(self, sample_ceh_json):
        """Test bounding box extraction."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert metadata.bounding_box is not None
        assert metadata.bounding_box.west == pytest.approx(-8.648)
        assert metadata.bounding_box.east == pytest.approx(1.768)
        assert metadata.bounding_box.south == pytest.approx(49.864)
        assert metadata.bounding_box.north == pytest.approx(60.861)
    
    def test_parse_temporal_extent(self, sample_ceh_json):
        """Test temporal extent extraction."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert metadata.temporal_extent is not None
        assert metadata.temporal_extent.start_date == date(2020, 1, 1)
        assert metadata.temporal_extent.end_date == date(2023, 12, 31)
    
    def test_parse_keywords(self, sample_ceh_json):
        """Test keyword extraction from multiple fields."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert "water" in metadata.keywords
        assert "quality" in metadata.keywords
        assert "United Kingdom" in metadata.keywords
    
    def test_parse_topic_categories(self, sample_ceh_json):
        """Test topic category extraction."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        category_values = [tc.value if hasattr(tc, 'value') else tc for tc in metadata.topic_categories]
        assert "inlandWaters" in category_values
        assert "environment" in category_values
    
    def test_parse_responsible_parties(self, sample_ceh_json):
        """Test responsible party extraction."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert len(metadata.responsible_parties) == 2
        
        # First party has full name
        author = metadata.responsible_parties[0]
        assert author.name == "John Smith"
        assert author.organisation == "UKCEH"
        assert author.email == "john.smith@ceh.ac.uk"
        
        # Second party is org only
        publisher = metadata.responsible_parties[1]
        assert publisher.organisation == "UKCEH"
    
    def test_parse_distributions(self, sample_ceh_json):
        """Test distribution extraction."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert len(metadata.distributions) == 1
        dist = metadata.distributions[0]
        assert dist.url == "https://example.com/download.zip"
        assert dist.name == "Download data"
    
    def test_parse_relationships(self, sample_ceh_json):
        """Test relationship extraction."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert len(metadata.related_documents) == 1
        rel = metadata.related_documents[0]
        assert rel.identifier == "parent-dataset-uuid"
    
    def test_parse_supporting_documents(self, sample_ceh_json):
        """Test supporting document extraction."""
        parser = CEHJSONParser()
        metadata = parser.parse(sample_ceh_json)
        
        assert len(metadata.supporting_documents) == 1
        doc = metadata.supporting_documents[0]
        assert doc.url == "https://example.com/docs.zip"
    
    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises ParseError."""
        parser = CEHJSONParser()
        
        with pytest.raises(ParseError, match="Invalid JSON"):
            parser.parse("not valid json {{{")
    
    def test_missing_required_field(self):
        """Test that missing required field raises error."""
        parser = CEHJSONParser()
        
        with pytest.raises(ParseError):
            parser.parse('{"title": "Missing ID"}')
    
    def test_minimal_json(self):
        """Test parsing minimal valid JSON."""
        parser = CEHJSONParser()
        
        minimal = '{"id": "test-123", "title": "Minimal Dataset"}'
        metadata = parser.parse(minimal)
        
        assert metadata.identifier == "test-123"
        assert metadata.title == "Minimal Dataset"
        assert metadata.keywords == []
        assert metadata.bounding_box is None


# =============================================================================
# ISO 19115 XML Parser Tests
# =============================================================================

class TestISO19115Parser:
    """Tests for ISO 19115 XML parser."""
    
    def test_parse_complete_xml(self, sample_iso19115_xml):
        """Test parsing complete XML response."""
        parser = ISO19115Parser()
        metadata = parser.parse(sample_iso19115_xml)
        
        assert metadata.identifier == "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
        assert metadata.title == "UK River Water Quality Dataset"
        assert metadata.abstract == "Water quality measurements from UK rivers."
    
    def test_parse_bounding_box(self, sample_iso19115_xml):
        """Test bounding box extraction from XML."""
        parser = ISO19115Parser()
        metadata = parser.parse(sample_iso19115_xml)
        
        assert metadata.bounding_box is not None
        assert metadata.bounding_box.west == pytest.approx(-8.648)
        assert metadata.bounding_box.north == pytest.approx(60.861)
    
    def test_parse_temporal_extent(self, sample_iso19115_xml):
        """Test temporal extent extraction from XML."""
        parser = ISO19115Parser()
        metadata = parser.parse(sample_iso19115_xml)
        
        assert metadata.temporal_extent is not None
        assert metadata.temporal_extent.start_date == date(2020, 1, 1)
        assert metadata.temporal_extent.end_date == date(2023, 12, 31)
    
    def test_parse_keywords(self, sample_iso19115_xml):
        """Test keyword extraction from XML."""
        parser = ISO19115Parser()
        metadata = parser.parse(sample_iso19115_xml)
        
        assert "water" in metadata.keywords
        assert "quality" in metadata.keywords
    
    def test_parse_responsible_parties(self, sample_iso19115_xml):
        """Test responsible party extraction from XML."""
        parser = ISO19115Parser()
        metadata = parser.parse(sample_iso19115_xml)
        
        assert len(metadata.responsible_parties) >= 1
        party = metadata.responsible_parties[0]
        assert party.name == "John Smith"
        assert party.organisation == "UKCEH"
    
    def test_invalid_xml_raises_error(self):
        """Test that invalid XML raises ParseError."""
        parser = ISO19115Parser()
        
        with pytest.raises(ParseError, match="Invalid XML"):
            parser.parse("not valid xml <<<")
    
    def test_missing_identifier_raises_error(self):
        """Test that missing identifier raises error."""
        parser = ISO19115Parser()
        
        xml_no_id = '''<?xml version="1.0"?>
        <gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd">
        </gmd:MD_Metadata>'''
        
        with pytest.raises(ParseError, match="Missing fileIdentifier"):
            parser.parse(xml_no_id)


# =============================================================================
# Parser Registry Tests
# =============================================================================

class TestParserRegistry:
    """Tests for parser registry."""
    
    def test_get_parser_for_json(self):
        """Test getting parser for JSON content type."""
        registry = ParserRegistry()
        parser = registry.get_parser_for_content_type("application/json")
        
        assert parser is not None
        assert isinstance(parser, CEHJSONParser)
    
    def test_get_parser_for_xml(self):
        """Test getting parser for XML content type."""
        registry = ParserRegistry()
        parser = registry.get_parser_for_content_type("application/xml")
        
        assert parser is not None
        assert isinstance(parser, ISO19115Parser)
    
    def test_get_parser_for_gemini(self):
        """Test getting parser for GEMINI content type."""
        registry = ParserRegistry()
        parser = registry.get_parser_for_content_type("application/x-gemini+xml")
        
        assert parser is not None
        assert isinstance(parser, ISO19115Parser)
    
    def test_detect_json_format(self):
        """Test auto-detection of JSON format."""
        registry = ParserRegistry()
        parser = registry.detect_format('{"id": "test"}')
        
        assert parser is not None
        assert isinstance(parser, CEHJSONParser)
    
    def test_detect_xml_format(self):
        """Test auto-detection of XML format."""
        registry = ParserRegistry()
        parser = registry.detect_format('<?xml version="1.0"?><root/>')
        
        assert parser is not None
        assert isinstance(parser, ISO19115Parser)
    
    def test_parse_with_content_type(self, sample_ceh_json):
        """Test parsing with content type hint."""
        registry = ParserRegistry()
        metadata = registry.parse(sample_ceh_json, content_type="application/json")
        
        assert metadata.identifier == "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
    
    def test_parse_with_auto_detection(self, sample_ceh_json):
        """Test parsing with auto-detection."""
        registry = ParserRegistry()
        metadata = registry.parse(sample_ceh_json)
        
        assert metadata.identifier == "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
    
    def test_parse_unknown_format_raises_error(self):
        """Test that unknown format raises error."""
        registry = ParserRegistry()
        
        with pytest.raises(ParseError, match="No parser found"):
            registry.parse("random content", content_type="application/unknown")
    
    def test_available_parsers(self):
        """Test listing available parsers."""
        registry = ParserRegistry()
        parsers = registry.available_parsers
        
        assert "ceh_json" in parsers
        assert "iso19115" in parsers