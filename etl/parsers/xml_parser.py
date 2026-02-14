"""
Parser for ISO 19115 (UK GEMINI) XML metadata format.

Uses lxml for full-document parsing with XPath queries.
"""

from datetime import date, datetime
from typing import Any, Optional

from lxml import etree

from etl.models import (
    BoundingBox,
    DatasetMetadata,
    DistributionInfo,
    RelatedDocument,
    ResponsibleParty,
    TemporalExtent,
    TopicCategory,
)

from .base import MetadataParser, ParseError


class ISO19115Parser(MetadataParser):
    """
    Parser for ISO 19115 XML (UK GEMINI profile).

    Handles the XML response from:
    https://catalogue.ceh.ac.uk/id/{uuid}.xml?format=gemini

    Uses XPath for clean, readable element extraction.

    Example:
        parser = ISO19115Parser()
        metadata = parser.parse(xml_string)
    """

    # XML Namespaces used in ISO 19115 / GEMINI
    NAMESPACES = {
        "gmd": "http://www.isotc211.org/2005/gmd",
        "gco": "http://www.isotc211.org/2005/gco",
        "gml": "http://www.opengis.net/gml/3.2",
        "gmx": "http://www.isotc211.org/2005/gmx",
        "srv": "http://www.isotc211.org/2005/srv",
        "xlink": "http://www.w3.org/1999/xlink",
    }

    @property
    def format_name(self) -> str:
        return "iso19115"

    @property
    def supported_content_types(self) -> list[str]:
        return ["application/xml", "text/xml", "gemini"]

    def parse(self, content: str) -> DatasetMetadata:
        """
        Parse ISO 19115 XML content into DatasetMetadata.

        Args:
            content: Raw XML string

        Returns:
            Parsed DatasetMetadata object
        """
        try:
            # Parse XML
            root = etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            raise ParseError(f"Invalid XML: {e}", self.format_name, e)

        try:
            return self._build_metadata(root, content)
        except Exception as e:
            raise ParseError(f"Failed to parse: {e}", self.format_name, e)

    def _build_metadata(self, root: etree._Element, raw_content: str) -> DatasetMetadata:
        """Build DatasetMetadata from parsed XML."""
        return DatasetMetadata(
            identifier=self._get_identifier(root),
            title=self._get_title(root),
            abstract=self._get_abstract(root),
            lineage=self._get_lineage(root),
            keywords=self._get_keywords(root),
            topic_categories=self._get_topic_categories(root),
            bounding_box=self._get_bounding_box(root),
            temporal_extent=self._get_temporal_extent(root),
            responsible_parties=self._get_responsible_parties(root),
            distributions=self._get_distributions(root),
            source_format=self.format_name,
            raw_document=raw_content,
        )

    def _xpath(self, element: etree._Element, path: str) -> list:
        """Execute XPath query with namespaces."""
        return element.xpath(path, namespaces=self.NAMESPACES)

    def _xpath_text(self, element: etree._Element, path: str) -> Optional[str]:
        """Get text content from XPath query."""
        results = self._xpath(element, path)
        if results:
            if isinstance(results[0], str):
                return results[0].strip()
            elif hasattr(results[0], "text") and results[0].text:
                return results[0].text.strip()
        return None

    def _get_identifier(self, root: etree._Element) -> str:
        """Extract file identifier."""
        identifier = self._xpath_text(
            root,
            ".//gmd:fileIdentifier/gco:CharacterString/text()"
        )
        if not identifier:
            raise ParseError("Missing fileIdentifier", self.format_name)
        return identifier

    def _get_title(self, root: etree._Element) -> str:
        """Extract dataset title."""
        title = self._xpath_text(
            root,
            ".//gmd:identificationInfo//gmd:citation//gmd:title/gco:CharacterString/text()"
        )
        if not title:
            raise ParseError("Missing title", self.format_name)
        return title

    def _get_abstract(self, root: etree._Element) -> Optional[str]:
        """Extract dataset abstract."""
        return self._xpath_text(
            root,
            ".//gmd:identificationInfo//gmd:abstract/gco:CharacterString/text()"
        )

    def _get_lineage(self, root: etree._Element) -> Optional[str]:
        """Extract lineage/provenance information."""
        return self._xpath_text(
            root,
            ".//gmd:dataQualityInfo//gmd:lineage//gmd:statement/gco:CharacterString/text()"
        )

    def _get_keywords(self, root: etree._Element) -> list[str]:
        """Extract all keywords."""
        keywords = []

        keyword_elements = self._xpath(
            root,
            ".//gmd:identificationInfo//gmd:descriptiveKeywords//gmd:keyword/gco:CharacterString/text()"
        )

        for kw in keyword_elements:
            if kw and kw.strip():
                keywords.append(kw.strip())

        return keywords

    def _get_topic_categories(self, root: etree._Element) -> list[TopicCategory]:
        """Extract ISO topic categories."""
        categories = []

        category_elements = self._xpath(
            root,
            ".//gmd:identificationInfo//gmd:topicCategory/gmd:MD_TopicCategoryCode/text()"
        )

        for cat in category_elements:
            if cat:
                try:
                    categories.append(TopicCategory(cat.strip()))
                except ValueError:
                    pass  # Unknown category

        return categories

    def _get_bounding_box(self, root: etree._Element) -> Optional[BoundingBox]:
        """Extract geographic bounding box."""
        bbox_element = self._xpath(
            root,
            ".//gmd:identificationInfo//gmd:extent//gmd:geographicElement/gmd:EX_GeographicBoundingBox"
        )

        if not bbox_element:
            return None

        bbox = bbox_element[0]

        try:
            west = float(self._xpath_text(bbox, ".//gmd:westBoundLongitude/gco:Decimal/text()"))
            east = float(self._xpath_text(bbox, ".//gmd:eastBoundLongitude/gco:Decimal/text()"))
            south = float(self._xpath_text(bbox, ".//gmd:southBoundLatitude/gco:Decimal/text()"))
            north = float(self._xpath_text(bbox, ".//gmd:northBoundLatitude/gco:Decimal/text()"))

            return BoundingBox(west=west, east=east, south=south, north=north)
        except (TypeError, ValueError):
            return None

    def _get_temporal_extent(self, root: etree._Element) -> Optional[TemporalExtent]:
        """Extract temporal extent."""
        # Use local-name() to match regardless of namespace prefix
        time_periods = root.xpath(".//*[local-name()='TimePeriod']")

        if not time_periods:
            return None

        tp = time_periods[0]

        # Get begin and end positions
        begin_results = tp.xpath("*[local-name()='beginPosition']/text()")
        end_results = tp.xpath("*[local-name()='endPosition']/text()")

        begin = begin_results[0].strip() if begin_results else None
        end = end_results[0].strip() if end_results else None

        start_date = self._parse_date(begin)
        end_date = self._parse_date(end)

        if start_date or end_date:
            return TemporalExtent(
                start_date=start_date,
                end_date=end_date
            )
        return None

    def _parse_date(self, value: Optional[str]) -> Optional[date]:
        """Parse date from ISO format."""
        if not value:
            return None

        value = value.strip()

        for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y"]:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        # Try just the date portion
        if len(value) >= 10:
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                pass

        return None

    def _get_responsible_parties(self, root: etree._Element) -> list[ResponsibleParty]:
        """Extract responsible parties."""
        parties = []

        party_elements = self._xpath(
            root,
            ".//gmd:identificationInfo//gmd:pointOfContact/gmd:CI_ResponsibleParty"
        )

        # Also check citation contacts
        party_elements.extend(self._xpath(
            root,
            ".//gmd:identificationInfo//gmd:citation//gmd:citedResponsibleParty/gmd:CI_ResponsibleParty"
        ))

        for party in party_elements:
            name = self._xpath_text(party, ".//gmd:individualName/gco:CharacterString/text()")
            org = self._xpath_text(party, ".//gmd:organisationName/gco:CharacterString/text()")
            role = self._xpath_text(party, ".//gmd:role/gmd:CI_RoleCode/@codeListValue")
            email = self._xpath_text(
                party,
                ".//gmd:contactInfo//gmd:electronicMailAddress/gco:CharacterString/text()"
            )

            if name or org:
                parties.append(ResponsibleParty(
                    name=name,
                    organisation=org,
                    role=role or "other",
                    email=email,
                ))

        return parties

    def _get_distributions(self, root: etree._Element) -> list[DistributionInfo]:
        """Extract distribution/download options."""
        distributions = []

        transfer_elements = self._xpath(
            root,
            ".//gmd:distributionInfo//gmd:transferOptions//gmd:onLine/gmd:CI_OnlineResource"
        )

        for transfer in transfer_elements:
            url = self._xpath_text(transfer, ".//gmd:linkage/gmd:URL/text()")

            if not url:
                continue

            name = self._xpath_text(transfer, ".//gmd:name/gco:CharacterString/text()")
            description = self._xpath_text(transfer, ".//gmd:description/gco:CharacterString/text()")
            function = self._xpath_text(transfer, ".//gmd:function/gmd:CI_OnLineFunctionCode/@codeListValue")

            distributions.append(DistributionInfo(
                url=url,
                name=name,
                description=description,
                access_type=function or "other",
            ))

        return distributions