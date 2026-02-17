# Use specific version for reproducibility
FROM python:3.10-slim

# Set environment variables
# PYTHONDONTWRITEBYTECODE: Prevents Python from writing pyc files to disc
# PYTHONUNBUFFERED: Prevents Python from buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Safe default for HuggingFace cache
    HF_HOME=/app/model_cache

WORKDIR /app

# Install system dependencies
# libsndfile1 is required for soundfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser

# Copy application code
COPY . .

# Create necessary directories and set permissions
RUN mkdir -p model_cache uploaded_voices voices && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose the port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run the application with Gunicorn
# Workers will be overridden by docker-compose or gunicorn_config.py usually, 
# but we provide a sensible default here.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120", "server:app"]
