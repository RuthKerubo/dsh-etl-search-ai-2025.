FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY etl/ ./etl/
COPY api/ ./api/

# Create data directories
RUN mkdir -p /app/data/cache

# Expose API port
EXPOSE 8000

# Default to running API
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]