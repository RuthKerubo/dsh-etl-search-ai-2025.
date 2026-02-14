"""
Parser for CEH JSON metadata format.

The CEH catalogue returns a custom JSON format that includes all
metadata fields in a flat-ish structure.
"""

import json
from datetime import date, datetime
from typing import Any, Optional

from etl.models import (
    AccessType,
    BoundingBox,
    DatasetMetadata,
    DistributionInfo,
    RelatedDocument,
    RelationshipType,
    ResponsibleParty,
    SupportingDocument,
    TemporalExtent,
    TopicCategory,
)

from .base import MetadataParser, ParseError


class CEHJSONParser(MetadataParser):
    """
    Parser for CEH catalogue JSON format.

    Handles the JSON response from:
    https://catalogue.ceh.ac.uk/id/{uuid}?format=json

    Example:
        parser = CEHJSONParser()
        metadata = parser.parse(json_string)
    """

    @property
    def format_name(self) -> str:
        return "ceh_json"

    @property
    def supported_content_types(self) -> list[str]:
        return ["application/json", "json"]

    def parse(self, content: str) -> DatasetMetadata:
        """
        Parse CEH JSON content into DatasetMetadata.

        Args:
            content: Raw JSON string from CEH API

        Returns:
            Parsed DatasetMetadata object
        """
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ParseError(f"Invalid JSON: {e}", self.format_name, e)

        try:
            return self._build_metadata(data, content)
        except KeyError as e:
            raise ParseError(f"Missing required field: {e}", self.format_name, e)
        except Exception as e:
            raise ParseError(f"Failed to parse: {e}", self.format_name, e)

    def _build_metadata(self, data: dict[str, Any], raw_content: str) -> DatasetMetadata:
        """Build DatasetMetadata from parsed JSON."""
        return DatasetMetadata(
            identifier=data["id"],
            title=data["title"],
            abstract=data.get("description"),
            lineage=data.get("lineage"),
            keywords=self._parse_keywords(data),
            topic_categories=self._parse_topic_categories(data),
            bounding_box=self._parse_bounding_box(data),
            temporal_extent=self._parse_temporal_extent(data),
            responsible_parties=self._parse_responsible_parties(data),
            distributions=self._parse_distributions(data),
            related_documents=self._parse_relationships(data),
            supporting_documents=self._parse_supporting_documents(data),
            source_format=self.format_name,
            raw_document=raw_content,
        )

    def _parse_keywords(self, data: dict[str, Any]) -> list[str]:
        """Extract keywords from various keyword fields."""
        keywords = []

        # CEH uses multiple keyword fields
        keyword_fields = [
            "keywordsOther",
            "keywordsPlace",
            "keywordsProject",
            "keywordsTheme",
            "keywordsInstrument",
        ]

        for field in keyword_fields:
            if field in data:
                for kw in data[field]:
                    if isinstance(kw, dict) and "value" in kw:
                        keywords.append(kw["value"])
                    elif isinstance(kw, str):
                        keywords.append(kw)

        return keywords

    def _parse_topic_categories(self, data: dict[str, Any]) -> list[TopicCategory]:
        """Extract ISO topic categories."""
        categories = []

        for tc in data.get("topicCategories", []):
            value = tc.get("value") if isinstance(tc, dict) else tc
            if value:
                try:
                    categories.append(TopicCategory(value))
                except ValueError:
                    # Unknown category, skip
                    pass

        return categories

    def _parse_bounding_box(self, data: dict[str, Any]) -> Optional[BoundingBox]:
        """Extract geographic bounding box."""
        boxes = data.get("boundingBoxes", [])

        if not boxes:
            return None

        # Use first bounding box
        box = boxes[0]

        try:
            return BoundingBox(
                west=float(box["westBoundLongitude"]),
                east=float(box["eastBoundLongitude"]),
                south=float(box["southBoundLatitude"]),
                north=float(box["northBoundLatitude"]),
            )
        except (KeyError, ValueError, TypeError):
            return None

    def _parse_temporal_extent(self, data: dict[str, Any]) -> Optional[TemporalExtent]:
        """Extract temporal extent."""
        extents = data.get("temporalExtents", [])

        if not extents:
            return None

        # Use first temporal extent
        extent = extents[0]

        start_date = self._parse_date(extent.get("begin"))
        end_date = self._parse_date(extent.get("end"))

        if start_date is None and end_date is None:
            return None

        return TemporalExtent(
            start_date=start_date,
            end_date=end_date,
        )

    def _parse_date(self, value: Any) -> Optional[date]:
        """Parse date from various formats."""
        if not value:
            return None

        if isinstance(value, date):
            return value

        if isinstance(value, str):
            value = value.strip()
            # Try common formats
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y"]:
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
            # Try just the date portion for ISO timestamps
            if len(value) >= 10:
                try:
                    return datetime.strptime(value[:10], "%Y-%m-%d").date()
                except ValueError:
                    pass

        return None

    def _parse_responsible_parties(self, data: dict[str, Any]) -> list[ResponsibleParty]:
        """Extract responsible parties."""
        parties = []

        for party_data in data.get("responsibleParties", []):
            # Build name from parts
            name_parts = []
            if party_data.get("givenName"):
                name_parts.append(party_data["givenName"])
            if party_data.get("familyName"):
                name_parts.append(party_data["familyName"])

            name = " ".join(name_parts) if name_parts else None
            organisation = party_data.get("organisationName")

            # Skip if no identity
            if not name and not organisation:
                continue

            # Extract ORCID from nameIdentifier
            orcid = None
            name_id = party_data.get("nameIdentifier", "")
            if "orcid.org" in str(name_id):
                orcid = name_id

            parties.append(ResponsibleParty(
                name=name,
                organisation=organisation,
                role=party_data.get("role", "other"),
                email=party_data.get("email"),
                orcid=orcid,
            ))

        return parties

    def _parse_distributions(self, data: dict[str, Any]) -> list[DistributionInfo]:
        """Extract distribution/download options."""
        distributions = []

        for resource in data.get("onlineResources", []):
            url = resource.get("url")
            if not url:
                continue

            # Map CEH function to AccessType
            function = resource.get("function", "").lower()
            if function == "download":
                access_type = AccessType.DOWNLOAD
            elif function in ("fileaccess", "information"):
                access_type = AccessType.FILE_ACCESS
            elif function == "order":
                access_type = AccessType.ORDER
            else:
                access_type = AccessType.OTHER

            distributions.append(DistributionInfo(
                url=url,
                name=resource.get("name"),
                description=resource.get("description"),
                access_type=access_type,
            ))

        return distributions

    def _parse_relationships(self, data: dict[str, Any]) -> list[RelatedDocument]:
        """Extract relationships to other documents."""
        related = []

        for rel in data.get("relationships", []):
            target = rel.get("target")
            if not target:
                continue

            # Parse relationship type from relation URI
            relation_uri = rel.get("relation", "")
            rel_type = self._map_relationship_type(relation_uri)

            related.append(RelatedDocument(
                identifier=target,
                relationship_type=rel_type,
                url=rel.get("url"),
            ))

        return related

    def _map_relationship_type(self, relation_uri: str) -> RelationshipType:
        """Map CEH relation URI to RelationshipType."""
        uri_lower = relation_uri.lower()

        if "memberof" in uri_lower or "parent" in uri_lower:
            return RelationshipType.PARENT
        elif "child" in uri_lower:
            return RelationshipType.CHILD
        elif "supersedes" in uri_lower or "revision" in uri_lower:
            return RelationshipType.REVISION_OF
        elif "source" in uri_lower:
            return RelationshipType.SOURCE
        elif "series" in uri_lower:
            return RelationshipType.SERIES
        else:
            return RelationshipType.OTHER

    def _parse_supporting_documents(self, data: dict[str, Any]) -> list[SupportingDocument]:
        """Extract supporting document references."""
        documents = []

        for info in data.get("infoLinks", []):
            url = info.get("url")
            if not url:
                continue

            # Extract filename from URL
            filename = url.split("/")[-1] if "/" in url else url

            documents.append(SupportingDocument(
                filename=filename,
                url=url,
                description=info.get("name"),
            ))

        return documents