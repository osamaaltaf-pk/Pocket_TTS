"""Configuration settings for the Real-Time TTS Server."""

import os
from pathlib import Path

# Server Configuration
HOST = os.getenv("TTS_HOST", "127.0.0.1")
PORT = int(os.getenv("TTS_PORT", "8000"))

# Audio Configuration
SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "24000"))  # Pocket TTS default sample rate
CHUNK_SIZE = int(os.getenv("TTS_CHUNK_SIZE", "4800"))  # ~200ms chunks for streaming
AUDIO_FORMAT = os.getenv("TTS_AUDIO_FORMAT", "wav")

# Model Configuration
MODEL_CACHE_DIR = Path("./model_cache")
VOICE_CACHE_DIR = Path("./voices")
UPLOADED_VOICES_DIR = Path("./uploaded_voices")

# Pre-made voices from Pocket TTS
PREMADE_VOICES = [
    "alba",
    "marius",
    "javert",
    "jean",
    "fantine",
    "cosette",
    "eponine",
    "azelma",
]

# Performance Configuration
MAX_TEXT_LENGTH = 10000  # Maximum characters per request
STREAM_BUFFER_SIZE = 3  # Number of chunks to buffer before streaming

# Create necessary directories
MODEL_CACHE_DIR.mkdir(exist_ok=True)
VOICE_CACHE_DIR.mkdir(exist_ok=True)
UPLOADED_VOICES_DIR.mkdir(exist_ok=True)
