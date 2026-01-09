# DSH ETL Search AI

A semantic search application for environmental datasets from the UK Centre for Ecology & Hydrology (UKCEH).

## Features

- **ETL Pipeline**: Fetches and parses 200+ environmental datasets from CEH catalogue
- **Hybrid Search**: Combines semantic (AI embeddings) + keyword search
- **FastAPI Backend**: RESTful API with automatic fallback
- **SvelteKit Frontend**: Modern, fast, reactive UI
- **ChromaDB**: Vector store for semantic search
- **Cohere Embeddings**: AI-powered text understanding

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    SvelteKit Frontend                        │
│                    http://localhost:5173                     │
│                                                              │
│  - Search page with instant results                          │
│  - Dataset browser with pagination                           │
│  - Dataset detail view                                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                         │
│                    http://localhost:8000                     │
│                                                              │
│  GET /health          - Service status                       │
│  GET /api/datasets    - List datasets (paginated)            │
│  GET /api/datasets/id - Single dataset                       │
│  GET /api/search?q=   - Hybrid search                        │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
      │   SQLite    │ │  ChromaDB   │ │  Cohere API │
      │  (metadata) │ │ (vectors)   │ │ (embeddings)│
      └─────────────┘ └─────────────┘ └─────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for frontend)
- Cohere API key (free at https://cohere.com)

### Installation
```bash
# Clone repository
git clone https://github.com/RuthKerubo/dsh-etl-search-ai-2025.git
cd dsh-etl-search-ai-2025

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..

# Configure environment
cp .env.example .env
# Edit .env and add your COHERE_API_KEY
```

### Run ETL Pipeline
```bash
# Initialize database
python -m etl.cli init

# Fetch and store datasets (3-5 minutes)
python -m etl.cli run

# Generate embeddings (requires COHERE_API_KEY)
python -m etl.cli embed

# Check status
python -m etl.cli status
```

### Start Development Servers
```bash
# Terminal 1: Backend
uvicorn api.main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

- **Backend**: http://localhost:8000/docs
- **Frontend**: http://localhost:5173

### Using Docker (Recommended)
```bash
# Start everything
docker-compose up

# Or run in background
docker-compose up -d
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000

## API Usage

### Health Check
```bash
curl http://localhost:8000/health
```

### Search Datasets
```bash
# Hybrid search (semantic + keyword)
curl "http://localhost:8000/api/search?q=climate%20change"

# Force keyword-only
curl "http://localhost:8000/api/search?q=river&mode=keyword"
```

### List Datasets
```bash
curl "http://localhost:8000/api/datasets?page=1&page_size=10"
```

### Get Single Dataset
```bash
curl "http://localhost:8000/api/datasets/{identifier}"
```

## Project Structure
```
dsh-etl-search-ai-2025/
├── api/                    # FastAPI application
│   ├── main.py             # App entry point
│   ├── dependencies.py     # Dependency injection
│   ├── routers/            # API routes
│   └── schemas/            # Pydantic models
├── etl/                    # ETL pipeline
│   ├── cli.py              # Command-line interface
│   ├── client/             # CEH API client
│   ├── embeddings/         # Cohere + ChromaDB
│   ├── models/             # Domain models
│   ├── parsers/            # JSON/XML parsers
│   ├── pipeline/           # ETL orchestration
│   ├── repository/         # Database access
│   └── search/             # Hybrid search
├── frontend/               # SvelteKit application
│   ├── src/
│   │   ├── routes/         # Pages
│   │   ├── lib/            # Components & utilities
│   │   └── app.html        # HTML template
│   ├── package.json
│   └── svelte.config.js
├── data/                   # Data storage
│   ├── metadata.db         # SQLite database
│   ├── chroma/             # Vector store
│   └── cache/              # API response cache
├── tests/                  # Test suite
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python -m etl.cli init` | Create database tables |
| `python -m etl.cli run` | Fetch and store datasets |
| `python -m etl.cli embed` | Generate embeddings |
| `python -m etl.cli status` | Show current status |
| `python -m etl.cli search "query"` | Test search |

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_PATH` | SQLite database path | `data/metadata.db` |
| `CHROMA_PATH` | ChromaDB storage path | `data/chroma` |
| `COHERE_API_KEY` | Cohere API key | Required for embeddings |
| `CACHE_DIR` | API cache directory | `data/cache` |
| `PUBLIC_API_URL` | Backend URL for frontend | `http://localhost:8000` |

## Search Modes

The search endpoint automatically selects the best mode:

- **Hybrid** (default): Combines semantic + keyword using Reciprocal Rank Fusion
- **Keyword-only**: Falls back when embeddings unavailable or rate-limited
- **Semantic-only**: Force with `?mode=semantic`

## Tech Stack

### Backend
- FastAPI
- SQLAlchemy
- Pydantic
- SQLite
- ChromaDB
- Cohere API

### Frontend
- SvelteKit
- TailwindCSS
- TypeScript

### DevOps
- Docker
- Docker Compose

## License

MIT

## Author

Ruth Kerubo - RSE Coding Task 2025