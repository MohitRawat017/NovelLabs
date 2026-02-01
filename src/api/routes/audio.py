"""
Audio API routes - handles TTS generation and audio streaming using Kokoro TTS
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_DIR = BASE_DIR / "audio"
SCRAPED_DIR = BASE_DIR / "data" / "output"

# Ensure audio directory exists
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# English voices only (from Kokoro_main.py)
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

# TTS generation jobs tracker
tts_jobs: dict = {}


class TTSRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    novel_slug: Optional[str] = None
    chapter_number: Optional[int] = None


@router.get("/voices")
async def list_voices():
    """List available English TTS voices"""
    return ENGLISH_VOICES


@router.get("/voices/flat")
async def list_voices_flat():
    """List all voices as a flat array"""
    all_voices = []
    for group, voices in ENGLISH_VOICES.items():
        for voice in voices:
            all_voices.append({"id": voice, "group": group})
    return all_voices


@router.get("/stream/{novel_slug}/{chapter_number}")
async def stream_chapter_audio(novel_slug: str, chapter_number: int):
    """Stream audio file for a chapter"""
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    
    if not audio_path.exists():
        raise HTTPException(
            status_code=404, 
            detail="Audio not generated yet. Use /generate to create audio first."
        )
    
    return FileResponse(
        audio_path,
        media_type="audio/wav",
        filename=f"{novel_slug}_chapter_{chapter_number}.wav"
    )


@router.get("/status/{novel_slug}/{chapter_number}")
async def check_audio_status(novel_slug: str, chapter_number: int):
    """Check if audio exists for a chapter"""
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    
    job_key = f"{novel_slug}_{chapter_number}"
    job = tts_jobs.get(job_key, {})
    
    return {
        "exists": audio_path.exists(),
        "generating": job.get("status") == "generating",
        "error": job.get("error")
    }


@router.post("/generate/{novel_slug}/{chapter_number}")
async def generate_chapter_audio(
    novel_slug: str, 
    chapter_number: int, 
    voice: str = "af_heart",
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Generate audio for a chapter using Kokoro TTS"""
    
    job_key = f"{novel_slug}_{chapter_number}"
    
    # Check if already generating
    if tts_jobs.get(job_key, {}).get("status") == "generating":
        return {"status": "already_generating", "message": "Audio generation in progress"}
    
    # Check for existing audio
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    if audio_path.exists():
        return {"status": "exists", "path": str(audio_path)}
    
    # Find chapter text file
    chapter_file = SCRAPED_DIR / novel_slug / f"Chapter_{chapter_number:04d}.txt"
    
    if not chapter_file.exists():
        raise HTTPException(status_code=404, detail="Chapter text file not found")
    
    # Read chapter text
    with open(chapter_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        content = '\n'.join(lines[3:]) if len(lines) > 3 else '\n'.join(lines)
    
    # Queue TTS generation
    tts_jobs[job_key] = {"status": "generating", "progress": 0}
    
    background_tasks.add_task(
        run_tts_generation, 
        novel_slug, 
        chapter_number, 
        content, 
        voice,
        job_key
    )
    
    return {
        "status": "queued",
        "message": f"Audio generation started for {novel_slug} chapter {chapter_number}",
        "voice": voice
    }


def run_tts_generation(novel_slug: str, chapter_number: int, text: str, voice: str, job_key: str):
    """Background task to generate TTS audio - splits into chunks for full chapter"""
    import sys
    import re
    import numpy as np
    
    try:
        # Add src directory to path for Kokoro_main import
        src_dir = Path(__file__).resolve().parent.parent.parent
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        
        from Kokoro_main import AudioBookGenerator
        import soundfile as sf
        
        # Create output directory
        output_dir = AUDIO_DIR / novel_slug
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"Chapter_{chapter_number:04d}.wav"
        
        # Initialize generator
        generator = AudioBookGenerator(voice=voice, output_dir=str(AUDIO_DIR), use_gpu=True)
        
        # Split text into chunks (by paragraphs or ~500 chars)
        chunks = split_text_into_chunks(text, max_length=500)
        logger.info(f"Processing {novel_slug} Ch.{chapter_number}: {len(chunks)} chunks")
        
        # Generate audio for each chunk
        audio_segments = []
        for idx, chunk in enumerate(chunks):
            tts_jobs[job_key] = {
                "status": "generating", 
                "progress": int((idx / len(chunks)) * 100)
            }
            
            audio = generator._synthesize(chunk)
            if audio is not None:
                audio_segments.append(audio)
                logger.info(f"  Chunk {idx + 1}/{len(chunks)} done")
            else:
                logger.warning(f"  Chunk {idx + 1}/{len(chunks)} failed")
        
        if audio_segments:
            # Combine segments with short silence between them
            silence = np.zeros(int(24000 * 0.3), dtype=np.float32)  # 0.3s pause
            combined = []
            for i, seg in enumerate(audio_segments):
                combined.append(seg)
                if i < len(audio_segments) - 1:
                    combined.append(silence)
            
            final_audio = np.concatenate(combined)
            sf.write(str(output_file), final_audio, 24000)
            
            duration = len(final_audio) / 24000
            tts_jobs[job_key] = {"status": "complete", "path": str(output_file)}
            logger.info(f"Generated audio: {output_file} ({duration:.1f}s)")
        else:
            tts_jobs[job_key] = {"status": "failed", "error": "No audio segments generated"}
            
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        tts_jobs[job_key] = {"status": "failed", "error": str(e)}


def split_text_into_chunks(text: str, max_length: int = 500) -> list:
    """Split text into chunks for TTS processing"""
    import re
    
    # Split by paragraphs first
    paragraphs = re.split(r'\n\s*\n', text.strip())
    
    chunks = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # If paragraph is short enough, use as-is
        if len(para) <= max_length:
            chunks.append(para)
        else:
            # Split by sentences
            sentences = re.split(r'(?<=[.!?])\s+', para)
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= max_length:
                    current_chunk = (current_chunk + " " + sentence).strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk)
    
    return chunks if chunks else [text[:max_length]]
