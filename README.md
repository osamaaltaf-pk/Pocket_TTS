<<<<<<< HEAD
# Real-Time TTS with Pocket TTS

A real-time text-to-speech system powered by [Pocket TTS](https://github.com/kyutai-labs/pocket-tts) with streaming audio, voice cloning, and a modern web interface.

## Features

- 🎙️ **Real-Time Streaming**: Low-latency audio streaming via WebSockets (~200ms to first chunk)
- 🎨 **Modern Web Interface**: Beautiful glassmorphism design with live audio playback
- 🔊 **Voice Cloning**: Upload custom voice samples for personalized speech
- ⚡ **CPU-Only**: No GPU required, runs efficiently on CPU
- 📊 **Performance Metrics**: Real-time display of latency and generation speed
- 🌊 **Streaming Audio**: Smooth playback with Web Audio API
- 💾 **Voice Management**: Pre-made voices + custom voice uploads

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or using `uv` (recommended):

```bash
uv pip install -r requirements.txt
```

### 2. Run the Server

```bash
python server.py
```

The server will start at `http://localhost:8000`

### 3. Open the Web Interface

Navigate to `http://localhost:8000` in your browser.

## Usage

### Web Interface

1. **Enter Text**: Type or paste text in the input area (max 10,000 characters)
2. **Select Voice**: Choose from pre-made voices or upload your own
3. **Generate**:
   - Click "Generate Speech" for complete audio file
   - Click "Stream Audio" for real-time streaming playback
4. **Download**: Save generated audio as WAV file

### Voice Cloning

1. Click "Upload Voice" button
2. Select an audio file (WAV, MP3, FLAC, OGG)
3. The voice will be processed and added to your voice library
4. Select your custom voice from the voice grid

**Tip**: For best results, [clean your audio sample](https://podcast.adobe.com/en/enhance) before uploading.

### API Endpoints

#### Generate Complete Audio
```bash
curl -X POST "http://localhost:8000/api/generate" \
  -d "text=Hello world" \
  -d "voice=alba" \
  --output output.wav
```

#### Upload Custom Voice
```bash
curl -X POST "http://localhost:8000/api/upload-voice" \
  -F "file=@my_voice.wav"
```

#### List Available Voices
```bash
curl "http://localhost:8000/api/voices"
```

#### WebSocket Streaming
Connect to `ws://localhost:8000/ws/stream` and send:
```json
{
  "text": "Hello world",
  "voice": "alba"
}
```

## Configuration

Edit `config.py` to customize:

- **Server Settings**: Host, port
- **Audio Parameters**: Sample rate, chunk size
- **Model Paths**: Cache directories
- **Performance**: Buffer size, max text length

## Pre-made Voices

The system includes 8 pre-made voices:
- `alba` - Default voice
- `marius`
- `javert`
- `jean`
- `fantine`
- `cosette`
- `eponine`
- `azelma`

See [voice licenses](https://huggingface.co/kyutai/tts-voices) for details.

## Performance

Typical performance on MacBook Air M4:
- **First Chunk Latency**: ~200ms
- **Generation Speed**: ~6x real-time
- **CPU Usage**: ~2 cores
- **Model Size**: 100M parameters

## Architecture

```
├── server.py           # FastAPI server with WebSocket support
├── tts_engine.py       # TTS engine wrapper with voice caching
├── config.py           # Configuration settings
├── requirements.txt    # Python dependencies
└── static/
    ├── index.html      # Web interface
    ├── style.css       # Modern UI styling
    └── app.js          # Client-side streaming logic
```

## Troubleshooting

### Model Download Issues
The first run will download the Pocket TTS model (~400MB). Ensure you have a stable internet connection.

### Audio Playback Issues
- Check browser console for errors
- Ensure WebSocket connection is established (green status indicator)
- Try refreshing the page

### Performance Issues
- Reduce chunk size in `config.py` for lower latency
- Increase chunk size for smoother playback
- Clear voice cache if memory usage is high

## Development

### Running in Development Mode

```bash
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Adding Custom Voices Programmatically

```python
from tts_engine import get_engine

engine = get_engine()
engine.export_voice("my_voice.wav", "my_voice.safetensors")
```

## Credits

- **Pocket TTS**: [Kyutai Labs](https://github.com/kyutai-labs/pocket-tts)
- **Paper**: [arXiv:2509.06926](https://arxiv.org/abs/2509.06926)
- **Tech Report**: [Kyutai Blog](https://kyutai.org/blog/2026-01-13-pocket-tts)

## License

This implementation is provided as-is. Please refer to the [Pocket TTS license](https://github.com/kyutai-labs/pocket-tts) for model usage terms.
=======
# Pocket_TTS
>>>>>>> b7f5be30fa2db3fc17b5ca46183e4709ef1961fe
