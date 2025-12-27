# CEH Catalogue URL Patterns

## VERIFIED PATTERNS

The CEH (Centre for Ecology & Hydrology) Environmental Information Data Centre
(EIDC) Catalogue provides metadata in multiple formats. These patterns have been
**verified by testing against live endpoints**.

**Base URL:** `https://catalogue.ceh.ac.uk`

## Dataset Identifier Format

Dataset identifiers are UUIDs, e.g., `be0bdc0e-bc2e-4f1d-b524-2c02798dd893`

---

## Metadata URL Patterns

For a dataset ID like `f710bed1-e564-47bf-b82c-4c2a2fe2810e`:

### 1. HTML Page (Human-readable)
```
https://catalogue.ceh.ac.uk/documents/{uuid}
```
**Example:** `https://catalogue.ceh.ac.uk/documents/f710bed1-e564-47bf-b82c-4c2a2fe2810e`

### 2. JSON Format (CEH Custom) VERIFIED
```
https://catalogue.ceh.ac.uk/id/{uuid}?format=json
```
**Example:** `https://catalogue.ceh.ac.uk/id/f710bed1-e564-47bf-b82c-4c2a2fe2810e?format=json`
**MIME Type:** `application/json`

### 3. ISO 19115 XML (UK GEMINI Profile) VERIFIED
```
https://catalogue.ceh.ac.uk/id/{uuid}.xml?format=gemini
```
**Example:** `https://catalogue.ceh.ac.uk/id/f710bed1-e564-47bf-b82c-4c2a2fe2810e.xml?format=gemini`
**MIME Type:** `application/x-gemini+xml;charset=UTF-8`

### 4. Schema.org JSON-LD VERIFIED
```
https://catalogue.ceh.ac.uk/id/{uuid}?format=schema.org
```
**Example:** `https://catalogue.ceh.ac.uk/id/f710bed1-e564-47bf-b82c-4c2a2fe2810e?format=schema.org`

### 5. RDF Turtle VERIFIED
```
https://catalogue.ceh.ac.uk/id/{uuid}?format=ttl
```
**Example:** `https://catalogue.ceh.ac.uk/id/f710bed1-e564-47bf-b82c-4c2a2fe2810e?format=ttl`

---

## Data Access Patterns

### Supporting Documents (ZIP) VERIFIED
```
https://data-package.ceh.ac.uk/sd/{uuid}.zip
```
**Example:** `https://data-package.ceh.ac.uk/sd/f710bed1-e564-47bf-b82c-4c2a2fe2810e.zip`

### Data Download (Direct access)
```
https://catalogue.ceh.ac.uk/datastore/eidchub/{uuid}
https://catalogue.ceh.ac.uk/datastore/eidchub/{uuid}/{filename}
```
**Note:** Some datasets require authentication via username/password

---

## URL Pattern Summary Table

| Format | URL Pattern | MIME Type |
|--------|-------------|-----------|
| HTML | `/documents/{uuid}` | text/html |
| **JSON** | `/id/{uuid}?format=json` | application/json |
| **ISO 19115 XML** | `/id/{uuid}.xml?format=gemini` | application/x-gemini+xml |
| **JSON-LD** | `/id/{uuid}?format=schema.org` | application/ld+json |
| **RDF Turtle** | `/id/{uuid}?format=ttl` | text/turtle |
| **Supporting Docs** | `data-package.ceh.ac.uk/sd/{uuid}.zip` | application/zip |

---

## JSON Response Structure (Key Fields)
```json
{
  "id": "f710bed1-e564-47bf-b82c-4c2a2fe2810e",
  "title": "Dataset Title",
  "description": "Abstract text...",
  "lineage": "Provenance information...",
  
  "boundingBoxes": [{
    "westBoundLongitude": -8.648,
    "eastBoundLongitude": 1.768,
    "southBoundLatitude": 49.864,
    "northBoundLatitude": 60.861
  }],
  
  "temporalExtents": [{
    "begin": "1891-01-01",
    "end": "2015-11-30"
  }],
  
  "topicCategories": [{"value": "inlandWaters"}],
  
  "keywordsOther": [{"value": "drought"}, {"value": "river"}],
  "keywordsPlace": [{"value": "United Kingdom"}],
  
  "responsibleParties": [{
    "familyName": "Smith",
    "givenName": "K.A.",
    "organisationName": "Centre for Ecology & Hydrology",
    "role": "author"
  }],
  
  "onlineResources": [{
    "url": "https://catalogue.ceh.ac.uk/datastore/eidchub/...",
    "name": "Download the data",
    "function": "fileAccess"
  }],
  
  "relationships": [{
    "relation": "https://vocabs.ceh.ac.uk/eidc#memberOf",
    "target": "parent-uuid"
  }]
}
```

---

## Implementation Notes

1. **Prefer JSON format** - Most structured and easiest to parse
2. **Use `/id/` not `/documents/`** - The `/id/` endpoint supports format parameter
3. **Supporting docs as ZIP** - Download from `data-package.ceh.ac.uk`
4. **Authentication** - Some data files require CEH account
5. **Rate Limiting** - Add delays between requests (recommend 1 second)
6. **Caching** - Cache downloaded metadata locally