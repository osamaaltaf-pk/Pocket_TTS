"""FastAPI server for real-time TTS with WebSocket streaming."""

import asyncio
import io
import json
import time
from pathlib import Path
from typing import Optional

import numpy as np
import scipy.io.wavfile
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn

import config
from tts_engine import get_engine

from pydantic import BaseModel, Field
from typing import List, Optional, Union, Literal
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Concurrency control
# Limit concurrent generations to avoid CPU thrashing
# Adjust based on CPU cores. For PocketTTS 100M, 1-2 concurrent is often max for real-time on standard CPUs.
concurrency_semaphore = asyncio.Semaphore(2)

class OpenAISpeechRequest(BaseModel):
    model: str = "pocket-tts"
    input: str
    voice: str = "alba"
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "wav"
    speed: float = 1.0
    stream: bool = False

class GenerateRequest(BaseModel):
    text: str
    voice: str = "alba"
    format: str = "wav"
    max_tokens: int = 80

class BatchRequest(BaseModel):
    requests: List[GenerateRequest]

class BatchResponse(BaseModel):
    job_id: str
    status: str
    results: List[dict] = []

# Initialize FastAPI app
app = FastAPI(
    title="Real-Time TTS Server",
    description="Pocket TTS with streaming audio support",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Security
API_KEY = os.getenv("TTS_API_KEY")

@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    # Skip auth for health check and static files
    if request.url.path.startswith("/api/health") or request.url.path.startswith("/static") or request.url.path == "/" or request.url.path.startswith("/docs") or request.url.path.startswith("/openapi.json"):
        return await call_next(request)
        
    if API_KEY:
        key = request.headers.get("X-API-Key")
        if not key or key != API_KEY:
             # Also check Authorization header for Bearer token compatibility
            auth = request.headers.get("Authorization")
            if not auth or not auth.startswith("Bearer ") or auth.split(" ")[1] != API_KEY:
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing API Key"})
            
    return await call_next(request)

# Global TTS engine instance
tts_engine = None


@app.on_event("startup")
async def startup_event():
    """Initialize the TTS engine on startup."""
    global tts_engine
    print("=" * 60)
    print("Starting Real-Time TTS Server")
    print("=" * 60)
    tts_engine = get_engine()
    print(f"Server ready at http://{config.HOST}:{config.PORT}")
    print("=" * 60)


@app.get("/")
async def root():
    """Serve the main web interface."""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"
    
    if index_file.exists():
        return FileResponse(index_file)
    else:
        return {"message": "Real-Time TTS Server", "status": "running"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": tts_engine is not None,
        "sample_rate": tts_engine.sample_rate if tts_engine else None
    }


@app.get("/api/voices")
async def get_voices():
    """Get list of available voices."""
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS engine not initialized")
    
    voices = tts_engine.get_available_voices()
    return {"voices": voices}


from pydantic import BaseModel

# Moved to top of file


@app.post("/api/generate")
async def generate_audio(request: GenerateRequest):
    """
    Generate complete audio file from text.
    """
    text = request.text
    voice = request.voice
    max_tokens = request.max_tokens
    
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS engine not initialized")
    
    if not text or len(text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    try:
        # Generate audio
        start_time = time.time()
        audio = tts_engine.generate(text, voice, stream=False, max_tokens=max_tokens)
        generation_time = time.time() - start_time
        
        # Convert to WAV format
        buffer = io.BytesIO()
        scipy.io.wavfile.write(buffer, tts_engine.sample_rate, audio)
        buffer.seek(0)
        
        # Calculate metrics
        audio_duration = len(audio) / tts_engine.sample_rate
        rtf = generation_time / audio_duration if audio_duration > 0 else 0
        
        return StreamingResponse(
            buffer,
            media_type="audio/wav",
            headers={
                "X-Generation-Time": str(generation_time),
                "X-Audio-Duration": str(audio_duration),
                "X-RTF": str(rtf),
                "Content-Disposition": f'attachment; filename="tts_output.wav"'
            }
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/audio/speech")
async def openai_speech(request: OpenAISpeechRequest):
    """
    OpenAI-compatible speech endpoint.
    Compatible with LiveKit and OpenAI SDKs.
    """
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS engine unavailable")

    async with concurrency_semaphore:
        if request.stream:
            return StreamingResponse(
                stream_generator(request.input, request.voice, 80), # Default max_tokens for stream
                media_type="audio/wav"
            )
        else:
            # Complete generation in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            try:
                # Run blocking generation in executor
                audio = await loop.run_in_executor(
                    None, 
                    lambda: tts_engine.generate(request.input, request.voice, stream=False)
                )
                
                # Convert to WAV/requested format
                import io
                import scipy.io.wavfile
                
                buffer = io.BytesIO()
                scipy.io.wavfile.write(buffer, tts_engine.sample_rate, audio)
                buffer.seek(0)
                
                return StreamingResponse(
                    buffer, 
                    media_type="audio/wav",
                    headers={"Content-Disposition": "attachment; filename=speech.wav"}
                )
            except Exception as e:
                print(f"Generation error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

async def stream_generator(text: str, voice: str, max_tokens: int):
    """Generator for streaming responses"""
    import io
    import scipy.io.wavfile
    
    # We yield wav headers first? No, for streaming raw audio, usually PCM or simple chunked wav is tricky.
    # But browsers/clients often handle "stream of wav chunks" or just raw pcm.
    # OpenAI returns chunks of the requested format.
    # For simplicity, we stream raw PCM or WAV loop?
    # Let's stream PCM bytes for compatibility with most raw consumers, OR
    # wrap each chunk in a mini-wav (bad overhead).
    # Best practice for modern streaming is usually just raw PCM or MP3 frames.
    # PocketTTS yields raw float32/int16 samples.
    
    try:
        # Preamble (WAV header) - difficult if length unknown.
        # So we skip WAV header for streaming and assume client handles raw or we use a container like MP3/Ogg if supported.
        # But user requested WAV.
        # We will stream raw samples for now, LiveKit agents usually handle raw or framing.
        
        for chunk in tts_engine.generate(text, voice, stream=True, max_tokens=max_tokens):
            # chunk is numpy array. Convert to bytes.
            yield chunk.tobytes()
            await asyncio.sleep(0) # Yield to event loop
            
    except Exception as e:
        print(f"Streaming error: {e}")

@app.post("/v1/audio/batch")
async def batch_generate(request: BatchRequest):
    """
    Generate audio for multiple texts in batch.
    Requests are processed sequentially.
    """
    results = []
    
    # We process sequentially to avoid OOM/thrashing
    # In a real production app, this would queue a Celery job.
    # Here, for "Launch MVP", we process async but await them.
    
    for req in request.requests:
        try:
            # Generate (reuse openai logic or direct)
            # We'll call the direct generate endpoint logic internally or just call engine
             audio = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: tts_engine.generate(req.text, req.voice, stream=False)
            )
             # Encode to base64 for JSON response
             import base64
             import io
             import scipy.io.wavfile
             
             buf = io.BytesIO()
             scipy.io.wavfile.write(buf, tts_engine.sample_rate, audio)
             b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
             
             results.append({
                 "text": req.text,
                 "status": "success",
                 "audio_base64": b64
             })
        except Exception as e:
             results.append({
                 "text": req.text,
                 "status": "error",
                 "error": str(e)
             })
             
    return {"results": results}


@app.post("/api/upload-voice")
async def upload_voice(file: UploadFile = File(...)):
    """
    Upload a custom voice sample for cloning.
    
    Args:
        file: Audio file (WAV, MP3, etc.)
    """
    if not tts_engine:
        raise HTTPException(status_code=503, detail="TTS engine not initialized")
    
    # Validate file type
    allowed_extensions = {".wav", ".mp3", ".flac", ".ogg"}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    try:
        # Save uploaded file
        file_path = config.UPLOADED_VOICES_DIR / file.filename
        content = await file.read()
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Optionally export to safetensors for faster loading
        safetensors_path = file_path.with_suffix(".safetensors")
        tts_engine.export_voice(file_path, safetensors_path)
        
        return {
            "success": True,
            "filename": file.filename,
            "voice_name": file_path.stem,
            "path": str(file_path),
            "embedding_path": str(safetensors_path)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time audio streaming.
    
    Protocol:
        Client sends: {"text": "...", "voice": "alba"}
        Server sends: {"type": "audio", "data": [...]} or {"type": "done", "metrics": {...}}
    """
    await websocket.accept()
    
    try:
        while True:
            # Receive request from client
            data = await websocket.receive_text()
            request = json.loads(data)
            
            text = request.get("text", "")
            voice = request.get("voice", "alba")
            max_tokens = int(request.get("max_tokens", 80))
            
            if not text:
                await websocket.send_json({
                    "type": "error",
                    "message": "Text cannot be empty"
                })
                continue
            
            # Generate and stream audio
            try:
                start_time = time.time()
                first_chunk_time = None
                total_samples = 0
                
                # Stream audio chunks
                for chunk in tts_engine.generate(text, voice, stream=True, max_tokens=max_tokens):
                    if first_chunk_time is None:
                        first_chunk_time = time.time() - start_time
                    
                    total_samples += len(chunk)
                    
                    # Send audio chunk as JSON (convert to list for JSON serialization)
                    await websocket.send_json({
                        "type": "audio",
                        "data": chunk.tolist(),
                        "sample_rate": tts_engine.sample_rate
                    })
                    
                    # Yield control to event loop without artificial delay
                    await asyncio.sleep(0)
                
                # Send completion message with metrics
                total_time = time.time() - start_time
                audio_duration = total_samples / tts_engine.sample_rate
                rtf = total_time / audio_duration if audio_duration > 0 else 0
                
                await websocket.send_json({
                    "type": "done",
                    "metrics": {
                        "total_time": total_time,
                        "first_chunk_latency": first_chunk_time,
                        "audio_duration": audio_duration,
                        "rtf": rtf,
                        "samples": total_samples
                    }
                })
            
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
    
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")


# Mount static files directory
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def main():
    """Run the server."""
    uvicorn.run(
        "server:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
