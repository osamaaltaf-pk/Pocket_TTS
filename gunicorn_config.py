import multiprocessing
import os

# Server socket
# Railway provides PORT env var.
port = os.getenv("PORT", "8000")
bind = f"0.0.0.0:{port}"

# Worker configurations
# For CPU-bound TTS, workers = 2-4 is usually good.
# We default to 3, but allow override via env var.
workers = int(os.getenv("GUNICORN_WORKERS", "3"))

# Worker class
# Uvicorn worker is required for ASGI/FastAPI
worker_class = "uvicorn.workers.UvicornWorker"

# Threads per worker
# For async I/O, 1 thread is standard.
threads = 1

# Timeout
# TTS generation can take time, so we increase timeout to 120s
timeout = 120
graceful_timeout = 120

# Keepalive for robust connections
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process naming
proc_name = "pocket-tts-production"

# Preload app to save memory (Shared memory for torch model?)
# Warning: Preload can cause issues with CUDA/multiprocessing if not careful.
# For CPU-only PyTorch, preloading *might* save RAM but `fork` safety is tricky.
# We disable it by default for safety, let workers load model independently.
preload_app = False
