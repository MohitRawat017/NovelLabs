"""
NovelLabs TTS Microservice for Lightning AI
Stateless service: text → audio → R2 → URL

This service:
- Loads Kokoro model ONCE at startup
- Accepts text + voice + segment_id (opaque string)
- Generates audio via Kokoro TTS
- Uploads to Cloudflare R2
- Returns audio URL

Environment Variables:
- USE_GPU: Toggle GPU/CPU acceleration (default: true)
- R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
"""

import os
import io
import logging
from contextlib import asynccontextmanager

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .r2_upload import upload_audio_to_r2

# Logging setup
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== Configuration ====================

USE_GPU = os.getenv("USE_GPU", "true").lower() == "true"
SAMPLE_RATE = 24000

# Available voices (English only for now)
ENGLISH_VOICES = {
    "American English (Female)": [
        "af_alloy", "af_aoede", "af_bella", "af_heart", "af_jessica",
        "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky"
    ],
    "American English (Male)": [
        "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
        "am_michael", "am_onyx", "am_puck", "am_santa"
    ],
    "British English (Female)": [
        "bf_alice", "bf_emma", "bf_isabella", "bf_lily"
    ],
    "British English (Male)": [
        "bm_daniel", "bm_fable", "bm_george", "bm_lewis"
    ]
}

# Flatten voices for validation
ALL_VOICES = [v for voices in ENGLISH_VOICES.values() for v in voices]

# ==================== Global Model State ====================

# Model loaded once at startup, reused for all requests
kokoro_pipeline = None


def load_model():
    """Load Kokoro model once at startup."""
    global kokoro_pipeline
    
    logger.info(f"Loading Kokoro TTS model (GPU: {USE_GPU})...")
    
    try:
        from kokoro import KPipeline
        
        # Select device
        if USE_GPU and torch.cuda.is_available():
            device = "cuda"
            logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            if USE_GPU:
                logger.warning("GPU requested but not available, falling back to CPU")
            else:
                logger.info("Using CPU (GPU disabled via USE_GPU=false)")
        
        # Initialize pipeline - model loads here
        kokoro_pipeline = KPipeline(lang_code='a')  # 'a' for American English
        
        logger.info("✓ Kokoro model loaded successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to load Kokoro model: {e}")
        raise RuntimeError(f"Model initialization failed: {e}")


def synthesize(text: str, voice: str) -> tuple[np.ndarray, float]:
    """
    Synthesize audio from text using Kokoro TTS.
    Returns (audio_array, duration_seconds)
    """
    if kokoro_pipeline is None:
        raise RuntimeError("Model not loaded")
    
    # Generate audio
    audio_segments = []
    for _, _, audio in kokoro_pipeline(text, voice=voice):
        audio_segments.append(audio)
    
    if not audio_segments:
        raise ValueError("No audio generated")
    
    # Concatenate segments
    audio = np.concatenate(audio_segments) if len(audio_segments) > 1 else audio_segments[0]
    duration = len(audio) / SAMPLE_RATE
    
    return audio, duration


# ==================== FastAPI App ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model on startup, cleanup on shutdown."""
    load_model()
    yield
    logger.info("Shutting down TTS service")


app = FastAPI(
    title="NovelLabs TTS Service",
    description="Stateless TTS microservice using Kokoro. Text in → Audio URL out.",
    version="1.0.0",
    lifespan=lifespan
)


# ==================== Request/Response Models ====================

class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    segment_id: str  # Opaque string - do not assume any structure or sequencing


class SynthesizeResponse(BaseModel):
    audio_url: str
    duration: float
    sample_rate: int


# ==================== Endpoints ====================

@app.get("/")
async def health_check():
    """Health check endpoint."""
    model_loaded = kokoro_pipeline is not None
    return {
        "status": "healthy" if model_loaded else "unhealthy",
        "model_loaded": model_loaded,
        "gpu_enabled": USE_GPU,
        "gpu_available": torch.cuda.is_available()
    }


@app.get("/voices")
async def list_voices():
    """List available TTS voices grouped by accent."""
    return ENGLISH_VOICES


@app.get("/voices/flat")
async def list_voices_flat():
    """List all voices as a flat array."""
    return [{"id": v, "group": g} for g, voices in ENGLISH_VOICES.items() for v in voices]


@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_audio(request: SynthesizeRequest):
    """
    Generate audio from text and upload to R2.
    
    - text: Text to synthesize
    - voice: Voice ID (e.g., "af_heart")
    - segment_id: Opaque identifier for the audio file (used as filename)
    
    Returns URL to the uploaded audio file.
    """
    # Validate voice
    if request.voice not in ALL_VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice '{request.voice}'. Use /voices to see available options."
        )
    
    # Validate text
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    if len(request.text) > 5000:
        raise HTTPException(status_code=400, detail="Text too long (max 5000 chars)")
    
    try:
        # Synthesize audio
        logger.info(f"Synthesizing: voice={request.voice}, segment_id={request.segment_id}, len={len(request.text)}")
        audio, duration = synthesize(request.text, request.voice)
        
        # Convert to WAV bytes
        buffer = io.BytesIO()
        sf.write(buffer, audio, SAMPLE_RATE, format='WAV')
        buffer.seek(0)
        audio_bytes = buffer.read()
        
        # Upload to R2
        # segment_id is treated as opaque - we just use it as filename
        audio_url = upload_audio_to_r2(
            audio_bytes=audio_bytes,
            filename=f"{request.segment_id}.wav"
        )
        
        logger.info(f"✓ Generated {duration:.2f}s audio → {audio_url}")
        
        return SynthesizeResponse(
            audio_url=audio_url,
            duration=round(duration, 3),
            sample_rate=SAMPLE_RATE
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Synthesis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


# ==================== Run with Uvicorn ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
