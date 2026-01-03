#!/usr/bin/env python3
"""Minimal embedding test."""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

print("Step 1: Imports...")
from etl.repository import SessionFactory, DatabaseConfig, DatasetRepository
print("  ✅ Repository imported")

print("\nStep 2: Load datasets...")
db_path = os.getenv("DATABASE_PATH", "data/metadata.db")
factory = SessionFactory(DatabaseConfig(database_path=db_path))
repo = DatasetRepository(factory)
datasets = repo.get_all()
print(f"  ✅ Loaded {len(datasets)} datasets")

print("\nStep 3: Import Cohere...")
from etl.embeddings import CohereEmbeddingService
print("  ✅ Cohere imported")

print("\nStep 4: Import ChromaDB (this might hang)...")
sys.stdout.flush()
import chromadb
print("  ✅ ChromaDB imported")

print("\nStep 5: Create embedding service...")
api_key = os.getenv("COHERE_API_KEY")
embedding_service = CohereEmbeddingService(api_key=api_key)
print(f"  ✅ Using model: {embedding_service.model_name}")

print("\nStep 6: Initialize VectorStore (this might hang)...")
sys.stdout.flush()
from etl.embeddings import VectorStore
store = VectorStore(
    embedding_service=embedding_service,
    persist_path="data/chroma",
    batch_size=10,
)
print("  ✅ VectorStore initialized")

print("\nStep 7: Embed just 5 datasets as test...")
import asyncio

async def test_embed():
    result = await store.add_datasets(datasets[:5], skip_existing=True)
    return result

result = asyncio.run(test_embed())
print(f"  ✅ Embedded {len(result.successful)} datasets")

print("\n✅ All steps completed!")