#!/usr/bin/env python3
"""
DSH ETL Search AI - Command Line Interface

Usage:
    python -m etl.cli init                    # Create database tables
    python -m etl.cli run                     # Run ETL pipeline (fetch, parse, store)
    python -m etl.cli embed                   # Generate embeddings (requires COHERE_API_KEY)
    python -m etl.cli status                  # Show current status
    python -m etl.cli search "query"          # Test search
"""

import asyncio
import os
import sys
from dotenv import load_dotenv
from pathlib import Path
from datetime import timedelta
load_dotenv()


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_dataset_ids(filepath: str = "data/metadata-file-identifiers.txt") -> list[str]:
    """Load dataset IDs from file."""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ File not found: {filepath}")
        sys.exit(1)
    
    ids = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    print(f"📋 Loaded {len(ids)} dataset IDs from {filepath}")
    return ids


def cmd_init():
    """Initialize database tables."""
    from etl.repository import SessionFactory, DatabaseConfig
    
    db_path = os.getenv("DATABASE_PATH", "data/metadata.db")
    
    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    config = DatabaseConfig(database_path=db_path)
    factory = SessionFactory(config)
    factory.init_db()
    
    print(f"✅ Database initialized: {db_path}")
    print("   Tables created: datasets, keywords, responsible_parties, etc.")


def cmd_run(ids_file: str = "data/metadata-file-identifiers.txt"):
    """Run the ETL pipeline."""
    from etl.client import CEHCatalogueClient
    from etl.parsers import get_default_registry
    from etl.repository import SessionFactory, DatabaseConfig
    from etl.pipeline import ETLPipeline, PipelineConfig, create_console_progress
    
    # Load IDs
    dataset_ids = load_dataset_ids(ids_file)
    
    # Setup
    db_path = os.getenv("DATABASE_PATH", "data/metadata.db")
    cache_dir = os.getenv("CACHE_DIR", "data/cache")
    
    print(f"📁 Database: {db_path}")
    print(f"📁 Cache: {cache_dir}")
    print()
    
    # Initialize
    factory = SessionFactory(DatabaseConfig(database_path=db_path))
    factory.init_db()
    
    client = CEHCatalogueClient(
        cache_dir=cache_dir,
        cache_ttl=timedelta(hours=24),
        concurrency=3,
        request_delay=0.3,
    )
    
    pipeline = ETLPipeline(
        client=client,
        parser_registry=get_default_registry(),
        session_factory=factory,
        config=PipelineConfig(batch_size=20),
    )
    
    # Run
    print("🚀 Starting ETL pipeline...")
    print()
    
    async def run_pipeline():
        return await pipeline.run(
            dataset_ids,
            progress_callback=create_console_progress(),
        )
    
    result = asyncio.run(run_pipeline())
    
    print()
    print(result.summary())
    
    if result.failed:
        print()
        print("❌ Failed datasets:")
        for f in result.failed[:10]:  # Show first 10
            print(f"   {f.dataset_id}: {f.error_message}")
        if len(result.failed) > 10:
            print(f"   ... and {len(result.failed) - 10} more")
    
    return result


def cmd_embed():
    """Generate embeddings for all datasets."""
    api_key = os.getenv("COHERE_API_KEY")
    
    if not api_key:
        print("❌ COHERE_API_KEY environment variable not set")
        print()
        print("To get an API key:")
        print("  1. Go to https://dashboard.cohere.com/api-keys")
        print("  2. Create a free account")
        print("  3. Copy your API key")
        print("  4. Set it: export COHERE_API_KEY=your-key")
        print()
        print("Or run without embeddings (keyword search only):")
        print("  The API will still work, just without semantic search.")
        sys.exit(1)
    
    from etl.embeddings import CohereEmbeddingService, VectorStore, create_indexing_progress
    from etl.repository import SessionFactory, DatabaseConfig, DatasetRepository
    
    db_path = os.getenv("DATABASE_PATH", "data/metadata.db")
    chroma_path = os.getenv("CHROMA_PATH", "data/chroma")
    
    print(f"📁 Database: {db_path}")
    print(f"📁 ChromaDB: {chroma_path}")
    print()
    
    # Get datasets from repository
    factory = SessionFactory(DatabaseConfig(database_path=db_path))
    repo = DatasetRepository(factory)
    
    datasets = repo.get_all_for_embedding()
    
    if not datasets:
        print("❌ No datasets in database. Run 'python -m etl.cli run' first.")
        sys.exit(1)
    
    print(f"📊 Found {len(datasets)} datasets to embed")
    print()
    
    # Setup embedding service
    embedding_service = CohereEmbeddingService(api_key=api_key)
    store = VectorStore(
        embedding_service=embedding_service,
        persist_path=chroma_path,
        batch_size=20,  # Add this line - smaller batches
    )
    
    # Check existing
    existing = len(store.get_indexed_ids())
    if existing > 0:
        print(f"ℹ️  {existing} datasets already embedded (will skip)")
    
    print("🧠 Generating embeddings...")
    print()
    
    async def run_embedding():
        return await store.add_datasets(
            datasets,
            skip_existing=True,
            progress_callback=create_indexing_progress(),
        )
    
    result = asyncio.run(run_embedding())
    
    print()
    print(result.summary())
    
    # Show stats
    stats = store.get_stats()
    print()
    print(f"📊 Vector store: {stats['total_documents']} documents indexed")


def cmd_status():
    """Show current status."""
    from etl.repository import SessionFactory, DatabaseConfig, DatasetRepository
    
    db_path = os.getenv("DATABASE_PATH", "data/metadata.db")
    chroma_path = os.getenv("CHROMA_PATH", "data/chroma")
    
    print("📊 DSH ETL Search AI - Status")
    print("=" * 50)
    print()
    
    # Database status
    print("📁 Database")
    if Path(db_path).exists():
        factory = SessionFactory(DatabaseConfig(database_path=db_path))
        repo = DatasetRepository(factory)
        count = repo.count()
        print(f"   Path: {db_path}")
        print(f"   Datasets: {count}")
    else:
        print(f"   Path: {db_path}")
        print("   Status: ❌ Not created (run 'python -m etl.cli init')")
    
    print()
    
    # Vector store status
    print("🧠 Vector Store")
    if Path(chroma_path).exists():
        try:
            from etl.embeddings import CohereEmbeddingService, VectorStore
            
            # Try to load without API key (just for status)
            api_key = os.getenv("COHERE_API_KEY", "dummy")
            embedding_service = CohereEmbeddingService(api_key=api_key)
            store = VectorStore(
                embedding_service=embedding_service,
                persist_path=chroma_path,
            )
            stats = store.get_stats()
            print(f"   Path: {chroma_path}")
            print(f"   Indexed: {stats['total_documents']} documents")
        except Exception as e:
            print(f"   Path: {chroma_path}")
            print(f"   Status: ⚠️ Error loading ({e})")
    else:
        print(f"   Path: {chroma_path}")
        print("   Status: ❌ Not created (run 'python -m etl.cli embed')")
    
    print()
    
    # API key status
    print("🔑 Cohere API")
    if os.getenv("COHERE_API_KEY"):
        print("   Status: ✅ Key configured")
    else:
        print("   Status: ⚠️ Not configured (semantic search disabled)")
    
    print()


def cmd_search(query: str):
    """Test search functionality."""
    from etl.repository import SessionFactory, DatabaseConfig, DatasetRepository
    
    db_path = os.getenv("DATABASE_PATH", "data/metadata.db")
    chroma_path = os.getenv("CHROMA_PATH", "data/chroma")
    
    factory = SessionFactory(DatabaseConfig(database_path=db_path))
    repo = DatasetRepository(factory)
    
    print(f"🔍 Searching: \"{query}\"")
    print()
    
    # Try hybrid search if embeddings available
    api_key = os.getenv("COHERE_API_KEY")
    
    if api_key and Path(chroma_path).exists():
        try:
            from etl.embeddings import CohereEmbeddingService, VectorStore
            from etl.search import HybridSearchService
            
            embedding_service = CohereEmbeddingService(api_key=api_key)
            store = VectorStore(
                embedding_service=embedding_service,
                persist_path=chroma_path,
            )
            
            service = HybridSearchService(
                vector_store=store,
                repository=repo,
            )
            
            async def run_search():
                return await service.search(query, limit=5)
            
            response = asyncio.run(run_search())
            
            print(f"📊 Mode: Hybrid (semantic + keyword)")
            print(f"   Query type: {response.query_type.value}")
            print(f"   Semantic results: {response.total_semantic}")
            print(f"   Keyword results: {response.total_keyword}")
            print()
            
            if response.results:
                print("Results:")
                for i, r in enumerate(response.results, 1):
                    sources = []
                    if r.from_semantic:
                        sources.append(f"sem#{r.semantic_rank}")
                    if r.from_keyword:
                        sources.append(f"kw#{r.keyword_rank}")
                    
                    print(f"  {i}. [{r.hybrid_score:.4f}] {r.title[:60]}...")
                    print(f"     Sources: {', '.join(sources)}")
                    print(f"     ID: {r.dataset_id}")
                    print()
            else:
                print("No results found.")
            
            return  # Success, exit function
            
        except Exception as e:
            # Fallback to keyword on any error (including rate limits)
            print(f"⚠️  Hybrid search failed ({type(e).__name__}), falling back to keyword search")
            print()
    
    # Keyword only fallback
    results = repo.search(query, limit=5)
    
    print(f"📊 Mode: Keyword only")
    print()
    
    if results:
        print("Results:")
        for i, d in enumerate(results, 1):
            print(f"  {i}. {d.title[:60]}...")
            print(f"     ID: {d.identifier}")
            print()
    else:
        print("No results found.")
        
def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="DSH ETL Search AI CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m etl.cli init                    Create database tables
  python -m etl.cli run                     Run ETL pipeline
  python -m etl.cli embed                   Generate embeddings
  python -m etl.cli status                  Show status
  python -m etl.cli search "climate data"  Test search
        """,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # init
    subparsers.add_parser("init", help="Initialize database tables")
    
    # run
    run_parser = subparsers.add_parser("run", help="Run ETL pipeline")
    run_parser.add_argument(
        "--ids", "-i",
        default="data/metadata-file-identifiers.txt",
        help="File containing dataset IDs",
    )
    
    # embed
    subparsers.add_parser("embed", help="Generate embeddings (requires COHERE_API_KEY)")
    
    # status
    subparsers.add_parser("status", help="Show current status")
    
    # search
    search_parser = subparsers.add_parser("search", help="Test search")
    search_parser.add_argument("query", help="Search query")
    
    args = parser.parse_args()
    
    if args.command == "init":
        cmd_init()
    elif args.command == "run":
        cmd_run(args.ids)
    elif args.command == "embed":
        cmd_embed()
    elif args.command == "status":
        cmd_status()
    elif args.command == "search":
        cmd_search(args.query)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()