# DSH ETL Search AI 2025

A dataset search and discovery solution using semantic and conversational capabilities, built for the CEH (Centre for Ecology & Hydrology) Catalogue.

## Overview

This project demonstrates:
- **ETL Pipeline**: Extraction of metadata from CEH Catalogue (ISO 19115 XML, JSON, JSON-LD, RDF)
- **Semantic Search**: Vector embeddings for dataset discovery
- **Web Interface**: Search and explore datasets using natural language
- **Conversational Agent**: Chat-based dataset discovery (bonus feature)

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python, FastAPI |
| Database | SQLite (metadata), ChromaDB (vectors) |
| Embeddings | sentence-transformers |
| Frontend | Vue 3, Tailwind CSS |
| LLM | Ollama (local) / OpenAI API |

## Project Structure

```
dsh-etl-search-ai-2025/
├── etl/                    # ETL Pipeline
│   ├── resources/          # Data source abstractions
│   ├── parsers/            # Format-specific parsers
│   ├── models/             # Domain models
│   ├── repositories/       # Database access layer
│   └── services/           # Pipeline orchestration
├── api/                    # FastAPI Backend
│   ├── routes/             # API endpoints
│   └── services/           # Business logic
├── frontend/               # Vue Application
├── tests/                  # Test suite
├── data/                   # Local data storage
│   ├── cache/              # Downloaded files cache
│   ├── metadata.db         # SQLite database
│   └── chroma/             # Vector store
└── docs/                   # Documentation
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- Git

### Installation

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/dsh-etl-search-ai-2025.git
cd dsh-etl-search-ai-2025
```

2. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the ETL pipeline:
```bash
python -m etl.main
```

5. Start the API server:
```bash
uvicorn api.main:app --reload
```

6. (Optional) Start the frontend:
```bash
cd frontend
npm install
npm run dev
```

## Usage

### ETL Pipeline

Process all datasets from the CEH Catalogue:
```bash
python -m etl.main --input metadata-file-identifiers.txt
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/search` | GET | Semantic search |
| `/chat` | POST | Conversational query |

### Search Example

```bash
curl "http://localhost:8000/search?q=flood+risk+assessment"
```

## Testing

Run the test suite:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=etl --cov=api
```

## Architecture

The system follows clean architecture principles with clear separation of concerns:

- **Resources**: Abstract data fetching (remote, local, cached)
- **Parsers**: Strategy pattern for multiple metadata formats
- **Repository**: Database access abstraction
- **Services**: Business logic orchestration

See [docs/architecture.md](docs/architecture.md) for detailed documentation.

## License

This project is created for the DSH RSE Code Evaluation Task.

## Acknowledgements

- [CEH Catalogue](https://catalogue.ceh.ac.uk/) for providing the metadata
- [sentence-transformers](https://www.sbert.net/) for embedding models
- [ChromaDB](https://www.trychroma.com/) for vector storage