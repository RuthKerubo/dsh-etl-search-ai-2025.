# DSH ETL Search AI

Dataset search and discovery platform with semantic and conversational capabilities. Extracts metadata from the CEH Environmental Information Data Centre, stores it in SQLite, generates vector embeddings, and provides hybrid search.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your COHERE_API_KEY

# Run ETL pipeline
python -m etl.cli run --ids metadata-file-identifiers.txt

# Generate embeddings
python -m etl.cli embed

# Start API server
python -m api.main
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend (Svelte)                             │
│                         Search & Discovery UI                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            API Layer                                    │
│                    FastAPI / REST Endpoints                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │   Hybrid    │ │   Vector    │ │ Repository  │
            │   Search    │ │   Store     │ │   Layer     │
            │   (RRF)     │ │  (ChromaDB) │ │  (SQLAlchemy)│
            └─────────────┘ └─────────────┘ └─────────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
            ┌─────────────┐                 ┌─────────────┐
            │   SQLite    │                 │  ChromaDB   │
            │  (metadata) │                 │  (vectors)  │
            └─────────────┘                 └─────────────┘
```

## Project Structure

```
etl/
├── client/                 # CEH Catalogue client
│   ├── ceh_client.py       # Async HTTP client with rate limiting
│   └── __init__.py
│
├── models/                 # Domain & ORM models
│   ├── dataset.py          # DatasetMetadata (Pydantic)
│   ├── user.py             # User, SearchHistory (Pydantic)
│   ├── orm.py              # SQLAlchemy ORM models
│   └── converters.py       # Domain ↔ ORM conversion
│
├── parsers/                # Metadata parsers
│   ├── base.py             # MetadataParser ABC, ParserRegistry
│   ├── json_parser.py      # CEH JSON format
│   └── iso19115.py         # ISO 19115 XML (UK GEMINI)
│
├── resources/              # Resource abstraction layer
│   ├── base.py             # Resource ABC, FetchResult
│   ├── http.py             # HttpResource, CEHCatalogueResource
│   ├── local.py            # LocalFileResource, ZipEntryResource
│   ├── cached.py           # CachedResource decorator
│   └── factory.py          # ResourceFactory
│
├── repository/             # Data access layer
│   ├── base.py             # Repository interfaces
│   ├── session.py          # SessionFactory, UnitOfWork
│   ├── dataset_repository.py
│   ├── user_repository.py
│   └── search_history_repository.py
│
├── embeddings/             # Vector embeddings
│   ├── base.py             # EmbeddingService ABC
│   ├── cohere_service.py   # Cohere API implementation
│   └── vector_store.py     # ChromaDB storage & search
│
├── search/                 # Search services
│   └── hybrid.py           # Hybrid search with RRF
│
├── pipeline/               # ETL orchestration
│   └── etl_pipeline.py     # ETLPipeline, ResumableETLPipeline
│
└── config.py               # Application settings
```

## Components

### 1. ETL Pipeline

Fetches metadata from CEH Catalogue, parses it, and stores in SQLite.

```python
from etl.pipeline import ETLPipeline, create_console_progress
from etl.client import CEHCatalogueClient
from etl.parsers import create_default_registry
from etl.repository import SessionFactory, DatabaseConfig

# Setup
session_factory = SessionFactory(DatabaseConfig("data/metadata.db"))
session_factory.init_db()

pipeline = ETLPipeline(
    client=CEHCatalogueClient(cache_dir="./data/cache"),
    parser_registry=create_default_registry(),
    session_factory=session_factory,
)

# Run
result = await pipeline.run(dataset_ids, progress_callback=create_console_progress())
print(result.summary())
```

**Features:**
- Async fetching with rate limiting (3 concurrent, 0.3s delay)
- Batch commits every 20 datasets
- Checkpoint support for resumable runs
- JSON + XML format support

### 2. Repository Layer

Unit of Work pattern for atomic database operations.

```python
from etl.repository import SessionFactory, DatabaseConfig, UnitOfWork

factory = SessionFactory(DatabaseConfig("data/metadata.db"))

# Atomic operations across repositories
with UnitOfWork(factory) as uow:
    uow.datasets.save(dataset)
    uow.users.save(user)
    uow.search_history.record_search("query", result_count=10)
    uow.commit()

# Simple reads
repo = DatasetRepository(factory)
dataset = repo.get("dataset-uuid")
results = repo.search("climate")
```

### 3. Embedding Service

Generates vector embeddings using Cohere API, stores in ChromaDB.

```python
from etl.embeddings import CohereEmbeddingService, VectorStore

embedding_service = CohereEmbeddingService(api_key=os.environ["COHERE_API_KEY"])
store = VectorStore(
    embedding_service=embedding_service,
    persist_path="./data/chroma",
)

# Index datasets
datasets = repository.get_all()
result = await store.add_datasets(datasets)

# Search
results = await store.search("drought conditions UK", limit=10)
```

**Configuration:**
- Model: `embed-english-v3.0` (1024 dimensions)
- Batch size: 96 (Cohere max)
- Storage: ChromaDB with cosine similarity

### 4. Hybrid Search

Combines semantic and keyword search using Reciprocal Rank Fusion.

```python
from etl.search import HybridSearchService

service = HybridSearchService(
    vector_store=store,
    repository=repository,
)

# Auto-detects query type and applies optimal strategy
response = await service.search("drought data UK")

for result in response.results:
    print(f"{result.hybrid_score:.4f} | {result.title}")
```

**Query Types (auto-detected):**
| Query | Type | Strategy |
|-------|------|----------|
| `f710bed1-e564-...` | EXACT_ID | Direct DB lookup |
| `"UK Drought Inventory"` | EXACT_TITLE | Keyword + boost |
| `rivers` | SHORT | Keyword weighted 1.5x |
| `climate change impacts` | NORMAL | 50/50 hybrid |

## Data Flow

```
CEH Catalogue API
       │
       ▼ (fetch JSON + XML)
┌─────────────────┐
│ CEHCatalogueClient │
└─────────────────┘
       │
       ▼ (parse)
┌─────────────────┐
│  ParserRegistry │
│  - CEHJSONParser│
│  - ISO19115Parser│
└─────────────────┘
       │
       ▼ (domain model)
┌─────────────────┐
│ DatasetMetadata │
└─────────────────┘
       │
       ├──────────────────────────────┐
       ▼                              ▼
┌─────────────────┐           ┌─────────────────┐
│ DatasetRepository│           │   VectorStore   │
│   (SQLAlchemy)  │           │   (ChromaDB)    │
└─────────────────┘           └─────────────────┘
       │                              │
       ▼                              ▼
   SQLite DB                    ChromaDB Store
  (structured)                   (embeddings)
       │                              │
       └──────────────┬───────────────┘
                      ▼
              ┌─────────────────┐
              │ HybridSearchService │
              │      (RRF)      │
              └─────────────────┘
                      │
                      ▼
                 Search Results
```

## Environment Variables

```env
# Required
COHERE_API_KEY=your-cohere-api-key

# Optional
DATABASE_PATH=data/metadata.db
CHROMA_PATH=data/chroma
CACHE_DIR=data/cache
LOG_LEVEL=INFO
```

## Database Schema

```sql
-- Core tables
datasets            -- Dataset metadata (title, abstract, etc.)
keywords            -- Unique keywords
dataset_keywords    -- M:N relationship
responsible_parties -- Organisations, contacts
online_resources    -- Download links, access URLs

-- User tables
users               -- User accounts
search_history      -- Search analytics
user_favourites     -- Bookmarked datasets
```

## API Endpoints (Planned)

```
GET  /api/datasets              # List datasets (paginated)
GET  /api/datasets/{id}         # Get single dataset
GET  /api/search?q=...          # Hybrid search
POST /api/search                # Advanced search with filters

GET  /api/users/me              # Current user
POST /api/users/favourites      # Add favourite
GET  /api/users/history         # Search history
```

## Development

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Type checking
mypy etl/

# Linting
ruff check etl/
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Domain models | Pydantic | Validation, serialization, IDE support |
| ORM | SQLAlchemy 2.0 | Type hints, relationship mapping |
| Vector store | ChromaDB | Simple, persistent, built-in search |
| Embeddings | Cohere | Good quality, free tier, fast |
| Search merge | RRF | No score normalization needed |
| HTTP client | aiohttp | Async, connection pooling |
| Transaction | Unit of Work | Atomic cross-repository ops |

## License

[Your License]

## Acknowledgments

- CEH Environmental Information Data Centre for the metadata API
- Cohere for the embedding API