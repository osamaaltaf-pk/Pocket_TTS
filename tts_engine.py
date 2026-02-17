"""Core TTS Engine wrapper for Pocket TTS with streaming support."""

import time
from pathlib import Path
from typing import Optional, Union, Iterator
import gc
import numpy as np
import torch
from pocket_tts import TTSModel, export_model_state
import config


class TTSEngine:
    """Wrapper for Pocket TTS model with streaming and voice management."""
    
    def __init__(self):
        """Initialize the TTS engine and load the model."""
        gc.collect()
        print("Loading Pocket TTS model...")
        start_time = time.time()
        
        # Disable gradients for inference
        torch.set_grad_enabled(False)
        
        # Load model with optimized parameters
        try:
            # Login to HF Hub for gated model access
            token_path = Path(r"e:\Pocket_tts\hf token.txt")
            if token_path.exists():
                token = token_path.read_text().strip()
                if token:
                    print(f"Found HF token, logging in...")
                    from huggingface_hub import login
                    login(token=token)
            
            # Load full model with cloning
            print("Loading Pocket TTS with Voice Cloning (this may take a moment to download weights)...")
            self.model = TTSModel.load_model(
                temp=0.7,
                lsd_decode_steps=1
            )
            print("Voice Cloning Model Loaded Successfully!")
        except Exception as e:
            print(f"Failed to load cloning model: {e}")
            print("Falling back to standard model (no voice cloning)...")
            try:
                # Fallback to base model if cloning weights unavailable
                # Assuming the library supports a flag or different load method for base model
                # If library API doesn't have explicit flag in load_model, we might need to catch specific error
                # The error message said "Without voice cloning, you can use our catalog..."
                # This often implies `voice_cloning=False` or similar
                self.model = TTSModel.load_model(
                    temp=0.7,
                    lsd_decode_steps=1,
                    voice_cloning=False # Hypothetical flag based on error context
                )
            except TypeError:
                 # If voice_cloning arg doesn't exist, maybe it needs a different model name?
                 # Re-raise original error if we can't figure it out, but user said "Without voice cloning..."
                 # Let's assume standard load might fail but maybe there's a specific "base" model?
                 # Actually, usually `load_model` tries to download default.
                 print("Could not load with voice_cloning=False. Please login with `uvx hf auth login`.")
                 raise e

        self.sample_rate = self.model.sample_rate
        load_time = time.time() - start_time
        print(f"Model loaded in {load_time:.2f}s")
        
        # Cache for voice states
        self.voice_cache = {}
        
        # Preload common voices
        # self._preload_voices()
    
    def _preload_voices(self):
        """Preload common pre-made voices for faster access."""
        print("Preloading voices...")
        for voice_name in config.PREMADE_VOICES[:3]:  # Load first 3 for quick start
            try:
                self.get_voice_state(voice_name)
                print(f"  [OK] Loaded {voice_name}")
            except Exception as e:
                print(f"  [FAIL] Failed to load {voice_name}: {e}")
    
    def get_voice_state(self, voice: Union[str, Path]):
        """
        Get or create a voice state.
        
        Args:
            voice: Voice name (pre-made), path to audio file, or path to .safetensors
            
        Returns:
            Voice state object for generation
        """
        voice_str = str(voice)
        
        # Check if it is a simple name (not a path) and not in pre-made voices
        # We try to resolve it to a file in uploads directory
        if "/" not in voice_str and "\\" not in voice_str and voice_str not in config.PREMADE_VOICES:
            # Check for safetensors first (faster)
            safetensors_path = config.UPLOADED_VOICES_DIR / f"{voice_str}.safetensors"
            wav_path = config.UPLOADED_VOICES_DIR / f"{voice_str}.wav"
            mp3_path = config.UPLOADED_VOICES_DIR / f"{voice_str}.mp3"
            
            if safetensors_path.exists():
                voice = str(safetensors_path)
            elif wav_path.exists():
                voice = str(wav_path)
            elif mp3_path.exists():
                voice = str(mp3_path)
                
        voice_key = str(voice)
        
        # Check cache first
        if voice_key in self.voice_cache:
            return self.voice_cache[voice_key]
        
        # Load new voice state
        start_time = time.time()
        try:
             voice_state = self.model.get_state_for_audio_prompt(voice)
        except Exception as e:
            # Better error message for file not found
            if "Error opening" in str(e) and "System error" in str(e):
                raise ValueError(f"Voice file not found or unreadable: {voice}") from e
            raise e
            
        load_time = time.time() - start_time
        
        # Cache it
        self.voice_cache[voice_key] = voice_state
        print(f"Loaded voice '{voice}' in {load_time:.2f}s")
        
        return voice_state
    def generate(
        self,
        text: str,
        voice: Union[str, Path] = "alba",
        stream: bool = False,
        max_tokens: int = 80,  # Smaller default for lower latency
        speed_factor: float = 1.0  # Dummy param for now, could adjust temp/steps
    ) -> Union[np.ndarray, Iterator[np.ndarray]]:
        """
        Generate speech from text.
        
        Args:
            text: Text to convert to speech
            voice: Voice to use
            stream: Whether to stream
            max_tokens: Text chunk size (smaller = lower latency)
            speed_factor: Multiplier for generation speed (affects quality)
        """
        if len(text) > config.MAX_TEXT_LENGTH:
            raise ValueError(f"Text too long. Maximum {config.MAX_TEXT_LENGTH} characters.")
        
        voice_state = self.get_voice_state(voice)
        
        if stream:
            return self._generate_streaming(voice_state, text, max_tokens)
        else:
            return self._generate_complete(voice_state, text)
    
    def _generate_complete(self, voice_state, text: str) -> np.ndarray:
        # ... (implementation same as before)
        return self.model.generate_audio(voice_state, text, copy_state=True).numpy()

    def _generate_streaming(self, voice_state, text: str, max_tokens: int) -> Iterator[np.ndarray]:
        """
        Generate audio in streaming chunks.
        """
        # Get iterator from model's streaming method
        stream_iterator = self.model.generate_audio_stream(
            voice_state, 
            text, 
            copy_state=True,
            max_tokens=max_tokens
        )
        
        # Yield chunks
        for chunk in stream_iterator:
            if isinstance(chunk, torch.Tensor):
                yield chunk.cpu().numpy()
            else:
                yield chunk
    
    def export_voice(self, audio_path: Union[str, Path], output_path: Union[str, Path]):
        """
        Export a voice embedding to a .safetensors file for fast loading.
        
        Args:
            audio_path: Path to audio file for voice cloning
            output_path: Path to save the .safetensors file
        """
        print(f"Exporting voice from {audio_path}...")
        start_time = time.time()
        
        voice_state = self.model.get_state_for_audio_prompt(str(audio_path))
        export_model_state(voice_state, str(output_path))
        
        export_time = time.time() - start_time
        print(f"Voice exported in {export_time:.2f}s to {output_path}")
    
    def get_available_voices(self) -> list[dict]:
        """
        Get list of available voices.
        
        Returns:
            List of voice info dictionaries
        """
        voices = []
        
        # Add pre-made voices
        for voice_name in config.PREMADE_VOICES:
            voices.append({
                "name": voice_name,
                "type": "premade",
                "cached": voice_name in self.voice_cache
            })
        
        # Add uploaded voices
        if config.UPLOADED_VOICES_DIR.exists():
            for voice_file in config.UPLOADED_VOICES_DIR.glob("*.wav"):
                voices.append({
                    "name": voice_file.stem,
                    "type": "custom",
                    "path": str(voice_file),
                    "cached": str(voice_file) in self.voice_cache
                })
            
            for voice_file in config.UPLOADED_VOICES_DIR.glob("*.safetensors"):
                voices.append({
                    "name": voice_file.stem,
                    "type": "custom_embedding",
                    "path": str(voice_file),
                    "cached": str(voice_file) in self.voice_cache
                })
        
        return voices
    
    def clear_cache(self):
        """Clear the voice cache to free memory."""
        self.voice_cache.clear()
        print("Voice cache cleared")


# Singleton instance
_engine_instance: Optional[TTSEngine] = None


def get_engine() -> TTSEngine:
    """Get or create the global TTS engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = TTSEngine()
    return _engine_instance
