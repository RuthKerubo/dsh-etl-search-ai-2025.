"""
Tests for resource abstraction layer.

Includes:
- Unit tests with mocked HTTP responses
- Integration tests against real CEH API (optional)
- Error handling tests
"""
import json
import pytest
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from etl.resources import (
    ResourceFactory,
    HttpResource,
    LocalFileResource,
    ZipEntryResource,
    CachedResource,
    CEHCatalogueResource,
    CEHSupportingDocsResource,
    FetchResult,
    ResourceMetadata,
    ResourceType,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_ceh_json():
    """Sample CEH JSON response."""
    return {
        "id": "f710bed1-e564-47bf-b82c-4c2a2fe2810e",
        "title": "Test Dataset",
        "description": "A test dataset for unit testing",
        "boundingBoxes": [{
            "westBoundLongitude": -8.0,
            "eastBoundLongitude": 2.0,
            "southBoundLatitude": 49.0,
            "northBoundLatitude": 61.0,
        }],
        "temporalExtents": [{
            "begin": "2020-01-01",
            "end": "2023-12-31",
        }],
        "responsibleParties": [{
            "organisationName": "UKCEH",
            "role": "publisher",
        }],
    }


@pytest.fixture
def sample_iso19115_xml():
    """Sample ISO 19115 XML response."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco">
    <gmd:fileIdentifier>
        <gco:CharacterString>f710bed1-e564-47bf-b82c-4c2a2fe2810e</gco:CharacterString>
    </gmd:fileIdentifier>
    <gmd:identificationInfo>
        <gmd:MD_DataIdentification>
            <gmd:citation>
                <gmd:CI_Citation>
                    <gmd:title>
                        <gco:CharacterString>Test Dataset</gco:CharacterString>
                    </gmd:title>
                </gmd:CI_Citation>
            </gmd:citation>
            <gmd:abstract>
                <gco:CharacterString>A test dataset</gco:CharacterString>
            </gmd:abstract>
        </gmd:MD_DataIdentification>
    </gmd:identificationInfo>
</gmd:MD_Metadata>"""


# =============================================================================
# FetchResult Tests
# =============================================================================

class TestFetchResult:
    """Tests for FetchResult dataclass."""
    
    def test_successful_result(self):
        """Test creating successful result."""
        result = FetchResult(
            content=b'{"test": true}',
            metadata=ResourceMetadata(content_type="application/json"),
            success=True,
        )
        assert result.success
        assert result.text == '{"test": true}'
        assert result.error is None
    
    def test_failed_result(self):
        """Test creating failed result."""
        result = FetchResult.failure("Connection timeout")
        assert not result.success
        assert result.error == "Connection timeout"
        assert result.content == b""
    
    def test_content_hash(self):
        """Test content hash generation."""
        result = FetchResult(
            content=b"test content",
            metadata=ResourceMetadata(),
        )
        hash1 = result.content_hash
        
        result2 = FetchResult(
            content=b"test content",
            metadata=ResourceMetadata(),
        )
        hash2 = result2.content_hash
        
        # Same content = same hash
        assert hash1 == hash2
        
        result3 = FetchResult(
            content=b"different content",
            metadata=ResourceMetadata(),
        )
        # Different content = different hash
        assert result3.content_hash != hash1
    
    def test_metadata_type_detection(self):
        """Test metadata content type detection."""
        json_meta = ResourceMetadata(content_type="application/json")
        assert json_meta.is_json
        assert not json_meta.is_xml
        
        xml_meta = ResourceMetadata(content_type="application/xml")
        assert xml_meta.is_xml
        assert not xml_meta.is_json
        
        gemini_meta = ResourceMetadata(content_type="application/x-gemini+xml")
        assert gemini_meta.is_xml


# =============================================================================
# Local File Resource Tests
# =============================================================================

class TestLocalFileResource:
    """Tests for local file resource."""
    
    @pytest.mark.asyncio
    async def test_read_json_file(self, tmp_path):
        """Test reading JSON file with correct metadata."""
        file_path = tmp_path / "data.json"
        content = '{"key": "value", "number": 42}'
        file_path.write_text(content)
        
        resource = LocalFileResource(file_path)
        result = await resource.fetch()
        
        assert result.success
        assert result.text == content
        assert result.metadata.is_json
        assert result.metadata.size_bytes == len(content)
        
        # Verify JSON is parseable
        parsed = json.loads(result.text)
        assert parsed["key"] == "value"
        assert parsed["number"] == 42
    
    @pytest.mark.asyncio
    async def test_read_xml_file(self, tmp_path, sample_iso19115_xml):
        """Test reading XML file with correct metadata."""
        file_path = tmp_path / "metadata.xml"
        file_path.write_text(sample_iso19115_xml)
        
        resource = LocalFileResource(file_path)
        result = await resource.fetch()
        
        assert result.success
        assert result.metadata.is_xml
        assert "MD_Metadata" in result.text
    
    @pytest.mark.asyncio
    async def test_file_not_found_error(self, tmp_path):
        """Test proper error for missing file."""
        resource = LocalFileResource(tmp_path / "nonexistent.json")
        
        assert not await resource.exists()
        
        result = await resource.fetch()
        assert not result.success
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_binary_file(self, tmp_path):
        """Test reading binary file."""
        file_path = tmp_path / "data.bin"
        binary_content = bytes(range(256))
        file_path.write_bytes(binary_content)
        
        resource = LocalFileResource(file_path)
        result = await resource.fetch()
        
        assert result.success
        assert result.content == binary_content


# =============================================================================
# ZIP Entry Resource Tests
# =============================================================================

class TestZipEntryResource:
    """Tests for ZIP entry resource."""
    
    @pytest.fixture
    def test_zip(self, tmp_path):
        """Create a test ZIP file."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "This is a readme file")
            zf.writestr("data/metadata.json", '{"id": "test-123"}')
            zf.writestr("docs/report.pdf", b"%PDF-1.4 fake pdf content")
        return zip_path
    
    @pytest.mark.asyncio
    async def test_read_text_entry(self, test_zip):
        """Test reading text file from ZIP."""
        resource = ZipEntryResource(test_zip, "readme.txt")
        
        assert await resource.exists()
        
        result = await resource.fetch()
        assert result.success
        assert result.text == "This is a readme file"
    
    @pytest.mark.asyncio
    async def test_read_json_entry(self, test_zip):
        """Test reading JSON from nested path in ZIP."""
        resource = ZipEntryResource(test_zip, "data/metadata.json")
        result = await resource.fetch()
        
        assert result.success
        
        data = json.loads(result.text)
        assert data["id"] == "test-123"
    
    @pytest.mark.asyncio
    async def test_entry_not_found(self, test_zip):
        """Test error for missing ZIP entry."""
        resource = ZipEntryResource(test_zip, "nonexistent.txt")
        
        assert not await resource.exists()
        
        result = await resource.fetch()
        assert not result.success
        assert "not found" in result.error.lower()
    
    def test_list_entries(self, test_zip):
        """Test listing all ZIP entries."""
        entries = ZipEntryResource.list_entries(test_zip)
        
        assert "readme.txt" in entries
        assert "data/metadata.json" in entries
        assert "docs/report.pdf" in entries
        assert len(entries) == 3
    
    def test_from_zip_factory(self, test_zip):
        """Test creating resources for all ZIP entries."""
        resources = ZipEntryResource.from_zip(test_zip)
        
        assert len(resources) == 3
        assert all(isinstance(r, ZipEntryResource) for r in resources)
    
    def test_from_zip_with_filter(self, test_zip):
        """Test filtering ZIP entries."""
        # Only JSON files
        resources = ZipEntryResource.from_zip(
            test_zip,
            filter_func=lambda name: name.endswith(".json")
        )
        
        assert len(resources) == 1
        assert resources[0].entry_name == "data/metadata.json"


# =============================================================================
# HTTP Resource Tests (Mocked)
# =============================================================================

class TestHttpResource:
    """Tests for HTTP resource with mocked responses."""
    
    @pytest.mark.asyncio
    async def test_successful_fetch(self, sample_ceh_json):
        """Test successful HTTP fetch."""
        resource = HttpResource("https://example.com/data.json")
        
        # Mock the _single_fetch method
        mock_result = FetchResult(
            content=json.dumps(sample_ceh_json).encode(),
            metadata=ResourceMetadata(
                content_type="application/json",
                size_bytes=100,
            ),
            success=True,
        )
        
        with patch.object(resource, '_single_fetch', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_result
            
            result = await resource.fetch()
            
            assert result.success
            assert result.metadata.is_json
            
            data = json.loads(result.text)
            assert data["id"] == "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
            assert data["title"] == "Test Dataset"
    
    @pytest.mark.asyncio
    async def test_http_404_error(self):
        """Test handling of 404 response."""
        resource = HttpResource("https://example.com/missing.json")
        
        mock_result = FetchResult(
            content=b"",
            metadata=ResourceMetadata(extra={"status_code": 404}),
            success=False,
            error="HTTP 404: Not Found",
        )
        
        with patch.object(resource, '_single_fetch', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_result
            
            result = await resource.fetch()
            
            assert not result.success
            assert "404" in result.error
    
    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        """Test retry logic on server error."""
        resource = HttpResource(
            "https://example.com/unstable.json",
            max_retries=3,
            retry_delay=0.01,  # Fast retry for testing
        )
        
        # First two calls fail with 500, third succeeds
        fail_result = FetchResult(
            content=b"",
            metadata=ResourceMetadata(extra={"status_code": 500}),
            success=False,
            error="HTTP 500: Internal Server Error",
        )
        success_result = FetchResult(
            content=b'{"ok": true}',
            metadata=ResourceMetadata(content_type="application/json"),
            success=True,
        )
        
        with patch.object(resource, '_single_fetch', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [fail_result, fail_result, success_result]
            
            result = await resource.fetch()
            
            assert result.success
            assert mock_fetch.call_count == 3  # Retried twice
    
    @pytest.mark.asyncio
    async def test_no_retry_on_404(self):
        """Test that 404 doesn't trigger retry."""
        resource = HttpResource(
            "https://example.com/missing.json",
            max_retries=3,
        )
        
        not_found_result = FetchResult(
            content=b"",
            metadata=ResourceMetadata(extra={"status_code": 404}),
            success=False,
            error="HTTP 404: Not Found",
        )
        
        with patch.object(resource, '_single_fetch', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = not_found_result
            
            result = await resource.fetch()
            
            assert not result.success
            assert mock_fetch.call_count == 1  # No retry for 404
    
    def test_invalid_url_scheme(self):
        """Test that invalid URL scheme raises error."""
        with pytest.raises(ValueError, match="Invalid URL scheme"):
            HttpResource("ftp://example.com/file.txt")


# =============================================================================
# CEH Catalogue Resource Tests
# =============================================================================

class TestCEHCatalogueResource:
    """Tests for CEH-specific resource."""
    
    def test_json_url_construction(self):
        """Test JSON URL is built correctly."""
        resource = CEHCatalogueResource(
            dataset_id="f710bed1-e564-47bf-b82c-4c2a2fe2810e",
            format="json",
        )
        
        expected = "https://catalogue.ceh.ac.uk/id/f710bed1-e564-47bf-b82c-4c2a2fe2810e?format=json"
        assert resource.url == expected
    
    def test_xml_url_construction(self):
        """Test ISO 19115 XML URL is built correctly."""
        resource = CEHCatalogueResource(
            dataset_id="f710bed1-e564-47bf-b82c-4c2a2fe2810e",
            format="gemini",
        )
        
        expected = "https://catalogue.ceh.ac.uk/id/f710bed1-e564-47bf-b82c-4c2a2fe2810e.xml?format=gemini"
        assert resource.url == expected
    
    def test_jsonld_url_construction(self):
        """Test JSON-LD URL is built correctly."""
        resource = CEHCatalogueResource(
            dataset_id="test-uuid",
            format="schema.org",
        )
        
        assert "format=schema.org" in resource.url
    
    def test_turtle_url_construction(self):
        """Test RDF Turtle URL is built correctly."""
        resource = CEHCatalogueResource(
            dataset_id="test-uuid",
            format="ttl",
        )
        
        assert "format=ttl" in resource.url
    
    def test_factory_methods(self):
        """Test convenience factory methods."""
        json_res = CEHCatalogueResource.json("test-uuid")
        assert json_res.format == "json"
        
        xml_res = CEHCatalogueResource.xml("test-uuid")
        assert xml_res.format == "gemini"
        
        jsonld_res = CEHCatalogueResource.jsonld("test-uuid")
        assert jsonld_res.format == "schema.org"
        
        ttl_res = CEHCatalogueResource.turtle("test-uuid")
        assert ttl_res.format == "ttl"
    
    @pytest.mark.asyncio
    async def test_fetch_json_response(self, sample_ceh_json):
        """Test fetching and parsing CEH JSON response."""
        resource = CEHCatalogueResource(
            dataset_id="f710bed1-e564-47bf-b82c-4c2a2fe2810e",
            format="json",
        )
        
        mock_result = FetchResult(
            content=json.dumps(sample_ceh_json).encode(),
            metadata=ResourceMetadata(content_type="application/json"),
            success=True,
        )
        
        with patch.object(resource, '_single_fetch', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_result
            
            result = await resource.fetch()
            
            assert result.success
            
            data = json.loads(result.text)
            assert data["title"] == "Test Dataset"
            assert len(data["boundingBoxes"]) == 1
            assert data["boundingBoxes"][0]["westBoundLongitude"] == -8.0


class TestCEHSupportingDocsResource:
    """Tests for CEH supporting docs resource."""
    
    def test_url_construction(self):
        """Test supporting docs URL is built correctly."""
        resource = CEHSupportingDocsResource(
            dataset_id="f710bed1-e564-47bf-b82c-4c2a2fe2810e"
        )
        
        expected = "https://data-package.ceh.ac.uk/sd/f710bed1-e564-47bf-b82c-4c2a2fe2810e.zip"
        assert resource.url == expected


# =============================================================================
# Cached Resource Tests
# =============================================================================

class TestCachedResource:
    """Tests for caching decorator."""
    
    @pytest.mark.asyncio
    async def test_cache_miss_then_hit(self, tmp_path):
        """Test that first fetch caches, second fetch returns cached."""
        source_path = tmp_path / "source.json"
        source_path.write_text('{"cached": false}')
        
        cache_dir = tmp_path / "cache"
        
        inner = LocalFileResource(source_path)
        cached = CachedResource(inner, cache_dir=cache_dir)
        
        # First fetch - cache miss
        result1 = await cached.fetch()
        assert result1.success
        assert not result1.from_cache
        
        # Modify source file (to prove we're reading from cache)
        source_path.write_text('{"cached": true, "modified": true}')
        
        # Second fetch - cache hit (should return OLD content)
        result2 = await cached.fetch()
        assert result2.success
        assert result2.from_cache
        assert result2.text == '{"cached": false}'  # Original content
    
    @pytest.mark.asyncio
    async def test_cache_ttl_expiry(self, tmp_path):
        """Test that expired cache is refreshed."""
        source_path = tmp_path / "source.txt"
        source_path.write_text("version 1")
        
        cache_dir = tmp_path / "cache"
        
        inner = LocalFileResource(source_path)
        cached = CachedResource(
            inner,
            cache_dir=cache_dir,
            ttl=timedelta(seconds=0),  # Immediate expiry
        )
        
        # First fetch
        result1 = await cached.fetch()
        assert result1.success
        
        # Update source
        source_path.write_text("version 2")
        
        # Second fetch - cache expired, should refetch
        result2 = await cached.fetch()
        assert result2.success
        assert result2.text == "version 2"
    
    @pytest.mark.asyncio
    async def test_fetch_fresh_bypasses_cache(self, tmp_path):
        """Test fetch_fresh always hits source."""
        source_path = tmp_path / "source.txt"
        source_path.write_text("original")
        
        cache_dir = tmp_path / "cache"
        
        inner = LocalFileResource(source_path)
        cached = CachedResource(inner, cache_dir=cache_dir)
        
        # Populate cache
        await cached.fetch()
        
        # Modify source
        source_path.write_text("updated")
        
        # fetch_fresh should get new content
        result = await cached.fetch_fresh()
        assert result.text == "updated"
        assert not result.from_cache
    
    @pytest.mark.asyncio
    async def test_cache_invalidation(self, tmp_path):
        """Test manual cache invalidation."""
        source_path = tmp_path / "source.txt"
        source_path.write_text("content")
        
        cache_dir = tmp_path / "cache"
        
        inner = LocalFileResource(source_path)
        cached = CachedResource(inner, cache_dir=cache_dir)
        
        # Populate cache
        await cached.fetch()
        
        # Invalidate
        deleted = await cached.invalidate()
        assert deleted
        
        # Update source
        source_path.write_text("new content")
        
        # Next fetch should read from source
        result = await cached.fetch()
        assert result.text == "new content"
        assert not result.from_cache
    
    @pytest.mark.asyncio
    async def test_cache_info(self, tmp_path):
        """Test cache statistics."""
        source_path = tmp_path / "source.txt"
        source_path.write_text("content")
        
        cache_dir = tmp_path / "cache"
        
        inner = LocalFileResource(source_path)
        cached = CachedResource(inner, cache_dir=cache_dir)
        
        # Before caching
        info = await cached.cache_info()
        assert not info["cached"]
        
        # After caching
        await cached.fetch()
        info = await cached.cache_info()
        assert info["cached"]
        assert info["valid"]


# =============================================================================
# Resource Factory Tests
# =============================================================================

class TestResourceFactory:
    """Tests for resource factory."""
    
    def test_creates_http_for_url(self):
        """Test factory creates HTTP resource for URLs."""
        factory = ResourceFactory(enable_caching=False)
        resource = factory.create("https://example.com/data.json")
        
        assert isinstance(resource, HttpResource)
    
    def test_creates_local_for_path(self, tmp_path):
        """Test factory creates local resource for paths."""
        factory = ResourceFactory(enable_caching=False)
        
        file_path = tmp_path / "test.json"
        file_path.write_text("{}")
        
        resource = factory.create(str(file_path))
        assert isinstance(resource, LocalFileResource)
    
    def test_creates_ceh_resource_for_ceh_url(self):
        """Test factory recognizes CEH URLs."""
        factory = ResourceFactory(enable_caching=False)
        
        url = "https://catalogue.ceh.ac.uk/id/f710bed1-e564-47bf-b82c-4c2a2fe2810e?format=json"
        resource = factory.create(url)
        
        assert isinstance(resource, CEHCatalogueResource)
    
    def test_wraps_with_cache_when_enabled(self, tmp_path):
        """Test factory wraps resources with cache."""
        factory = ResourceFactory(
            cache_dir=tmp_path / "cache",
            enable_caching=True,
        )
        
        resource = factory.create("https://example.com/data.json")
        assert isinstance(resource, CachedResource)
        assert isinstance(resource.wrapped, HttpResource)
    
    def test_ceh_metadata_convenience_method(self):
        """Test CEH metadata factory method."""
        factory = ResourceFactory(enable_caching=False)
        
        resource = factory.ceh_metadata(
            dataset_id="test-uuid",
            format="json",
        )
        
        assert isinstance(resource, CEHCatalogueResource)
        assert resource.dataset_id == "test-uuid"
        assert resource.format == "json"
    
    def test_ceh_supporting_docs_convenience_method(self):
        """Test CEH supporting docs factory method."""
        factory = ResourceFactory(enable_caching=False)
        
        resource = factory.ceh_supporting_docs("test-uuid")
        
        assert isinstance(resource, CEHSupportingDocsResource)


# =============================================================================
# Integration Tests (Optional - Hit Real API)
# =============================================================================

@pytest.mark.integration
class TestCEHIntegration:
    """
    Integration tests against real CEH API.
    
    Run with: pytest -m integration tests/test_resources.py -v
    Skip with: pytest -m "not integration" tests/test_resources.py -v
    """
    
    SAMPLE_DATASET_ID = "f710bed1-e564-47bf-b82c-4c2a2fe2810e"
    
    @pytest.mark.asyncio
    async def test_fetch_real_json(self):
        """Test fetching real JSON from CEH API."""
        resource = CEHCatalogueResource(
            dataset_id=self.SAMPLE_DATASET_ID,
            format="json",
        )
        
        result = await resource.fetch()
        
        assert result.success, f"Failed: {result.error}"
        assert result.metadata.is_json
        
        data = json.loads(result.text)
        assert "id" in data
        assert "title" in data
        assert data["id"] == self.SAMPLE_DATASET_ID
    
    @pytest.mark.asyncio
    async def test_fetch_real_xml(self):
        """Test fetching real ISO 19115 XML from CEH API."""
        resource = CEHCatalogueResource(
            dataset_id=self.SAMPLE_DATASET_ID,
            format="gemini",
        )
        
        result = await resource.fetch()
        
        assert result.success, f"Failed: {result.error}"
        assert result.metadata.is_xml
        assert "MD_Metadata" in result.text
    
    @pytest.mark.asyncio
    async def test_fetch_nonexistent_dataset(self):
        """Test error handling for non-existent dataset."""
        resource = CEHCatalogueResource(
            dataset_id="00000000-0000-0000-0000-000000000000",
            format="json",
        )
        
        result = await resource.fetch()
        
        # Should fail with 404-like error
        assert not result.success