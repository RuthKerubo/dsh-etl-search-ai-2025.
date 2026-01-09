# How to Run This Project

## Option 1: Docker (Easiest - 2 Commands)
```bash
# 1. Build
docker build -t dsh-etl-search .

# 2. Run
docker run -p 8000:8000 -v $(pwd)/data:/app/data -e COHERE_API_KEY=0aPSh20JSMBtcN0Ia9RbE9DFUCmPtJfLfBNgcEwJ dsh-etl-search
```

**Test it:** http://localhost:8000/docs

---

## Option 2: Python (3 Commands)
```bash
# 1. Setup
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt

# 2. Set API key
export COHERE_API_KEY=0aPSh20JSMBtcN0Ia9RbE9DFUCmPtJfLfBNgcEwJ

# 3. Run
uvicorn api.main:app --reload
```

**Test it:** http://localhost:8000/docs

---

## Try These
```bash
# Health check
curl http://localhost:8000/health

# Search
curl "http://localhost:8000/api/search?q=climate"

# Browse datasets
curl "http://localhost:8000/api/datasets?page=1&page_size=5"
```

---

## What It Does

- **200 environmental datasets** from UK Centre for Ecology & Hydrology
- **Hybrid search** combining AI (semantic) + keyword matching
- **REST API** with automatic documentation at `/docs`

---

*Ruth Kerubo - RSE Coding Task 2025*