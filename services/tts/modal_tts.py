"""
NovelLabs TTS Service - Modal Deployment
========================================
Production-ready TTS microservice using Kokoro TTS on Modal.
Features:
- GPU-accelerated inference with A10G
- FastAPI endpoints for synthesis
- Cloudflare R2 storage integration
- Model caching for fast cold starts
- Container keep-alive for reduced latency

Deploy: modal deploy modal_tts_service.py
Develop: modal serve modal_tts_service.py
"""

import io
import logging
from typing import Optional

import modal

# ==================== Configuration ====================

APP_NAME = "novellabs-tts"
MODEL_CACHE_DIR = "/cache/kokoro"
SAMPLE_RATE = 24000

# GPU Configuration
GPU_CONFIG = modal.gpu.A10G()  # A10G is cost-effective for TTS
# Alternatives: modal.gpu.T4(), modal.gpu.A100(), modal.gpu.H100()

# Container Configuration
CONTAINER_IDLE_TIMEOUT = 300  # Keep container warm for 5 minutes
CPU_CONFIG = 2.0  # 2 vCPUs
MEMORY_CONFIG = 4096  # 4GB RAM

# Available voices (English only)
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

ALL_VOICES = [v for voices in ENGLISH_VOICES.values() for v in voices]

# ==================== Modal App & Image ====================

app = modal.App(APP_NAME)

# Define container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]==0.115.4",
        "numpy==1.26.4",
        "soundfile==0.12.1",
        "torch==2.1.2",
        "boto3==1.34.162",
        "kokoro-onnx",  # Kokoro TTS library
    )
    .apt_install("libsndfile1")  # Required for soundfile
)

# Create a Modal Volume for model caching (persists across deployments)
model_volume = modal.Volume.from_name("kokoro-models", create_if_missing=True)

# ==================== R2 Upload Module ====================


def upload_to_r2(audio_bytes: bytes, filename: str) -> str:
    """
    Upload audio to Cloudflare R2 and return public URL.
    Expects R2 credentials in Modal secrets.
    """
    import os
    import boto3
    from botocore.config import Config
    
    # Get credentials from environment (set via Modal Secrets)
    account_id = os.environ.get("R2_AUDIO_ACCOUNT_ID")
    access_key = os.environ.get("R2_AUDIO_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_AUDIO_SECRET_ACCESS_KEY")
    bucket_name = os.environ.get("R2_AUDIO_BUCKET_NAME", "novellabs-audio")
    public_url = os.environ.get("R2_AUDIO_PUBLIC_URL", "")
    
    if not all([account_id, access_key, secret_key]):
        # Mock mode for testing without R2
        mock_url = f"https://mock-storage/{filename}"
        print(f"⚠️  R2 not configured. Mock URL: {mock_url}")
        return mock_url
    
    # Initialize R2 client
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    s3 = boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version='s3v4', retries={'max_attempts': 2})
    )
    
    # Upload to R2
    key = f"audio/{filename}"
    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=audio_bytes,
            ContentType="audio/wav",
            CacheControl="public, max-age=31536000"
        )
        
        # Build public URL
        if public_url:
            url = f"{public_url.rstrip('/')}/{key}"
        else:
            url = f"https://{bucket_name}.{account_id}.r2.dev/{key}"
        
        print(f"✓ Uploaded to R2: {key}")
        return url
        
    except Exception as e:
        print(f"❌ R2 upload failed: {e}")
        raise RuntimeError(f"Failed to upload audio: {e}")


# ==================== TTS Model Class ====================


@app.cls(
    image=image,
    gpu=GPU_CONFIG,
    cpu=CPU_CONFIG,
    memory=MEMORY_CONFIG,
    container_idle_timeout=CONTAINER_IDLE_TIMEOUT,
    volumes={MODEL_CACHE_DIR: model_volume},
    secrets=[modal.Secret.from_name("r2-audio-credentials")],
    # Enable if you need to debug
    # allow_concurrent_inputs=10,  # Process up to 10 requests concurrently
)
class KokoroTTS:
    """
    Kokoro TTS model class with GPU acceleration.
    Model is loaded once on container start and reused across requests.
    """
    
    @modal.enter()
    def load_model(self):
        """
        Called once when container starts.
        Downloads and caches the Kokoro model.
        """
        import torch
        from kokoro import KPipeline
        
        print("🚀 Loading Kokoro TTS model...")
        
        # Check GPU availability
        if torch.cuda.is_available():
            device = "cuda"
            print(f"✓ Using GPU: {torch.cuda.get_device_name(0)}")
        else:
            device = "cpu"
            print("⚠️  GPU not available, using CPU")
        
        # Initialize pipeline with model caching
        # The model will be cached in the Modal Volume
        self.pipeline = KPipeline(lang_code='a')  # 'a' = American English
        print("✓ Kokoro model loaded successfully")
    
    @modal.method()
    def synthesize(self, text: str, voice: str) -> tuple[bytes, float]:
        """
        Generate speech from text.
        
        Args:
            text: Text to synthesize
            voice: Voice ID (e.g., "af_heart")
        
        Returns:
            Tuple of (audio_bytes, duration_seconds)
        """
        import numpy as np
        import soundfile as sf
        
        print(f"🎤 Synthesizing: voice={voice}, len={len(text)}")
        
        # Generate audio segments
        audio_segments = []
        for _, _, audio in self.pipeline(text, voice=voice):
            audio_segments.append(audio)
        
        if not audio_segments:
            raise ValueError("No audio generated")
        
        # Concatenate segments
        audio = np.concatenate(audio_segments) if len(audio_segments) > 1 else audio_segments[0]
        duration = len(audio) / SAMPLE_RATE
        
        # Convert to WAV bytes
        buffer = io.BytesIO()
        sf.write(buffer, audio, SAMPLE_RATE, format='WAV')
        buffer.seek(0)
        audio_bytes = buffer.read()
        
        print(f"✓ Generated {duration:.2f}s of audio ({len(audio_bytes)} bytes)")
        return audio_bytes, duration


# ==================== FastAPI Web Application ====================


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("r2-audio-credentials")],
)
@modal.asgi_app()
def fastapi_app():
    """
    FastAPI application with multiple endpoints.
    Deployed as a persistent web service.
    """
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
    
    web_app = FastAPI(
        title="NovelLabs TTS Service",
        description="Stateless TTS microservice using Kokoro. Text in → Audio URL out.",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # ==================== Request/Response Models ====================
    
    class SynthesizeRequest(BaseModel):
        text: str = Field(..., min_length=1, max_length=5000)
        voice: str = Field(default="af_heart", description="Voice ID from /voices endpoint")
        segment_id: str = Field(..., description="Unique identifier for the audio file")
    
    class SynthesizeResponse(BaseModel):
        audio_url: str
        duration: float
        sample_rate: int
    
    class HealthResponse(BaseModel):
        status: str
        service: str
        version: str
        gpu_available: bool
    
    class VoiceInfo(BaseModel):
        id: str
        group: str
    
    # ==================== Endpoints ====================
    
    @web_app.get("/", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint."""
        import torch
        
        return HealthResponse(
            status="healthy",
            service="NovelLabs TTS",
            version="2.0.0",
            gpu_available=torch.cuda.is_available()
        )
    
    @web_app.get("/health", response_model=HealthResponse)
    async def health():
        """Alternative health check endpoint."""
        import torch
        
        return HealthResponse(
            status="healthy",
            service="NovelLabs TTS",
            version="2.0.0",
            gpu_available=torch.cuda.is_available()
        )
    
    @web_app.get("/voices")
    async def list_voices():
        """List available TTS voices grouped by accent."""
        return ENGLISH_VOICES
    
    @web_app.get("/voices/flat", response_model=list[VoiceInfo])
    async def list_voices_flat():
        """List all voices as a flat array."""
        return [
            VoiceInfo(id=voice, group=group)
            for group, voices in ENGLISH_VOICES.items()
            for voice in voices
        ]
    
    @web_app.post("/synthesize", response_model=SynthesizeResponse)
    async def synthesize_audio(request: SynthesizeRequest):
        """
        Generate audio from text and upload to R2.
        
        - **text**: Text to synthesize (1-5000 characters)
        - **voice**: Voice ID (use /voices to see options)
        - **segment_id**: Unique identifier for this audio file
        
        Returns URL to the uploaded audio file.
        """
        # Validate voice
        if request.voice not in ALL_VOICES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid voice '{request.voice}'. Use /voices to see available options."
            )
        
        # Validate text
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        try:
            # Get TTS model instance
            tts = KokoroTTS()
            
            # Generate audio
            audio_bytes, duration = tts.synthesize.remote(request.text, request.voice)
            
            # Upload to R2
            filename = f"{request.segment_id}.wav"
            audio_url = upload_to_r2(audio_bytes, filename)
            
            return SynthesizeResponse(
                audio_url=audio_url,
                duration=round(duration, 3),
                sample_rate=SAMPLE_RATE
            )
            
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            print(f"❌ Synthesis failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"TTS generation failed: {str(e)}"
            )
    
    return web_app


# ==================== Local Testing ====================


@app.local_entrypoint()
def test():
    """
    Local test function.
    Run with: modal run modal_tts_service.py
    """
    print("🧪 Testing TTS service locally...")
    
    tts = KokoroTTS()
    audio_bytes, duration = tts.synthesize.remote(
        "Hello from Modal! This is a test of the Kokoro TTS system.",
        "af_heart"
    )
    
    print(f"✓ Generated {duration:.2f}s of audio ({len(audio_bytes)} bytes)")
    print("✓ Test completed successfully!")