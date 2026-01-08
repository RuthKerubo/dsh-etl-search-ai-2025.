"""
DSH ETL Search AI - FastAPI Application.

Dataset search and discovery API with hybrid search capabilities.

Usage:
    uvicorn api.main:app --reload
    
    # Or
    python -m api.main
"""
from dotenv import load_dotenv
load_dotenv() 

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import init_dependencies, shutdown_dependencies
from api.routers import health, datasets, search


# =============================================================================
# Lifespan Management
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    
    Initializes dependencies on startup, cleans up on shutdown.
    """
    # Startup
    print("🚀 Starting DSH ETL Search AI...")
    init_dependencies()
    
    from api.dependencies import get_service_status
    status = get_service_status()
    
    print(f"   📁 Database: {'✓' if status['database'] else '✗'} ({status['dataset_count']} datasets)")
    print(f"   🧠 Vector store: {'✓' if status['vector_store'] else '✗'} ({status['indexed_count']} indexed)")
    print(f"   🔑 Embeddings: {'✓' if status['embedding_service'] else '✗ (keyword-only mode)'}")
    print()
    
    yield
    
    # Shutdown
    print("👋 Shutting down...")
    shutdown_dependencies()


# =============================================================================
# Application Setup
# =============================================================================

app = FastAPI(
    title="DSH ETL Search AI",
    description="""
Dataset search and discovery API for CEH Environmental Information Data Centre.

## Features
- **Hybrid Search**: Combines semantic (vector) and keyword search
- **Automatic Fallback**: Works without embeddings (keyword-only mode)
- **Pagination**: All list endpoints support pagination

## Search Modes
The `/search` endpoint automatically selects the best mode:
- **hybrid**: Semantic + keyword (when embeddings available)
- **keyword**: SQL LIKE matching (fallback)

You can force a mode with `?mode=keyword` or `?mode=semantic`.
    """,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Svelte dev server
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5000",  # Alternative
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Routers
# =============================================================================

app.include_router(health.router)
app.include_router(datasets.router, prefix="/api")
app.include_router(search.router, prefix="/api")


# =============================================================================
# Root Endpoint
# =============================================================================

@app.get("/")
def root():
    """API root - redirects to docs."""
    return {
        "name": "DSH ETL Search AI",
        "docs": "/docs",
        "health": "/health",
    }


# =============================================================================
# Run with Python
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )