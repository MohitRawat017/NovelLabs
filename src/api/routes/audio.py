"""
Audio API routes - handles TTS generation via external TTS service
Segments are stored per-chunk with audio_url pointing to R2 CDN

ARCHITECTURE:
- Render backend (this file): Orchestration, chunking, DB storage
- Lightning AI: Stateless TTS (text → audio → R2 → URL)
- Cloudflare R2: Audio file storage
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
import logging
import json
import httpx
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

# Import configuration
from ..config import TTS_SERVICE_URL, TTS_TIMEOUT

# Import database utilities
from ..database import get_db

# Base directories (for backward compatibility during migration)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_DIR = BASE_DIR / "audio"

# Ensure audio directory exists (for legacy files)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# English voices (fetched from TTS service, cached here as fallback)
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

# TTS generation jobs tracker (in-memory, not durable)
# TODO: Replace with Redis/Celery for durable background jobs in Phase 2
tts_jobs: dict = {}


class TTSRequest(BaseModel):
    text: str
    voice: str = "af_heart"
    novel_slug: Optional[str] = None
    chapter_number: Optional[int] = None


# ==================== Custom Exceptions ====================

class TTSServiceError(Exception):
    """Base exception for TTS service errors."""
    pass


class TTSUnavailableError(TTSServiceError):
    """TTS service is not reachable."""
    pass


class TTSTimeoutError(TTSServiceError):
    """TTS request timed out."""
    pass


# ==================== TTS Service Client ====================

async def call_tts_service(text: str, voice: str, segment_id: str) -> dict:
    """
    Call Lightning AI TTS service to synthesize audio.
    
    Returns:
        {
            "audio_url": "https://r2.../seg_123.wav",
            "duration": 3.2,
            "sample_rate": 24000
        }
    
    Raises:
        HTTPException on 4xx errors (do not retry)
        TTSUnavailableError on connection errors
        TTSTimeoutError on timeout
    """
    url = f"{TTS_SERVICE_URL}/synthesize"
    payload = {
        "text": text,
        "voice": voice,
        "segment_id": segment_id
    }
    
    # Retry logic: only retry on 5xx/network/timeout errors
    # Do NOT retry on 4xx errors (invalid text/voice)
    max_retries = 3
    last_error = None
    
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    url, 
                    json=payload, 
                    timeout=TTS_TIMEOUT
                )
                
                # 4xx errors: do not retry, fail immediately
                if 400 <= response.status_code < 500:
                    error_detail = response.json().get("detail", "Invalid request")
                    raise HTTPException(status_code=response.status_code, detail=error_detail)
                
                # 5xx errors: retry
                if response.status_code >= 500:
                    logger.warning(f"TTS service returned {response.status_code}, retry {attempt + 1}/{max_retries}")
                    last_error = f"TTS service error: {response.status_code}"
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except httpx.TimeoutException:
                logger.warning(f"TTS request timed out, retry {attempt + 1}/{max_retries}")
                last_error = "TTS request timed out"
                if attempt == max_retries - 1:
                    raise TTSTimeoutError(last_error)
                    
            except httpx.ConnectError:
                logger.error(f"Cannot connect to TTS service at {TTS_SERVICE_URL}")
                raise TTSUnavailableError(f"TTS service unavailable at {TTS_SERVICE_URL}")
    
    # All retries exhausted
    raise TTSTimeoutError(last_error or "TTS service failed after retries")


# ==================== Endpoints ====================

@router.get("/voices")
async def list_voices():
    """List available English TTS voices."""
    # Try to fetch from TTS service, fallback to cached list
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TTS_SERVICE_URL}/voices", timeout=5)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.warning(f"Could not fetch voices from TTS service: {e}")
    
    return ENGLISH_VOICES


@router.get("/voices/flat")
async def list_voices_flat():
    """List all voices as a flat array."""
    all_voices = []
    for group, voices in ENGLISH_VOICES.items():
        for voice in voices:
            all_voices.append({"id": voice, "group": group})
    return all_voices


@router.get("/stream/{novel_slug}/{chapter_number}")
async def stream_chapter_audio(novel_slug: str, chapter_number: int):
    """
    Stream/redirect to audio for a chapter.
    
    New behavior: Redirects to first segment's audio_url from R2.
    Legacy: Returns local file if it exists.
    """
    # Check for segments with audio URLs in database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.audio_url FROM segments s
            JOIN chapters c ON s.chapter_id = c.id
            JOIN novels n ON c.novel_id = n.id
            WHERE n.slug = ? AND c.chapter_number = ? AND s.status = 'ready'
            ORDER BY s.segment_index ASC
            LIMIT 1
        ''', (novel_slug, chapter_number))
        
        result = cursor.fetchone()
        if result and result['audio_url']:
            # Redirect to R2 CDN URL
            return RedirectResponse(url=result['audio_url'])
    
    # Legacy fallback: check local filesystem
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    
    if audio_path.exists():
        return FileResponse(
            audio_path,
            media_type="audio/wav",
            filename=f"{novel_slug}_chapter_{chapter_number}.wav"
        )
    
    raise HTTPException(
        status_code=404, 
        detail="Audio not generated yet. Use /generate to create audio first."
    )


@router.get("/status/{novel_slug}/{chapter_number}")
async def check_audio_status(novel_slug: str, chapter_number: int):
    """Check if audio exists for a chapter - checks both DB and filesystem."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get chapter_id
        cursor.execute('''
            SELECT c.id FROM chapters c
            JOIN novels n ON c.novel_id = n.id
            WHERE n.slug = ? AND c.chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Chapter not found")
        
        chapter_id = result['id']
        
        # Check if segments exist and are ready
        cursor.execute('''
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) as ready_count,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_count
            FROM segments
            WHERE chapter_id = ?
        ''', (chapter_id,))
        
        segment_stats = cursor.fetchone()
        has_segments = segment_stats['total'] > 0
        all_ready = segment_stats['total'] == segment_stats['ready_count'] if has_segments else False
        has_failures = segment_stats['failed_count'] > 0 if has_segments else False
    
    # Check filesystem as fallback
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    
    job_key = f"{novel_slug}_{chapter_number}"
    job = tts_jobs.get(job_key, {})
    
    return {
        "exists": all_ready or audio_path.exists(),
        "segments_in_db": has_segments,
        "segments_ready": all_ready,
        "segments_failed": has_failures,
        "audio_file_exists": audio_path.exists(),
        "generating": job.get("status") == "generating",
        "progress": job.get("progress", 0),
        "error": job.get("error")
    }


@router.get("/timings/{novel_slug}/{chapter_number}")
async def get_chapter_timings(novel_slug: str, chapter_number: int):
    """Get chunk timing data for karaoke-style highlighting - from database."""
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get chapter_id
        cursor.execute('''
            SELECT c.id FROM chapters c
            JOIN novels n ON c.novel_id = n.id
            WHERE n.slug = ? AND c.chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        result = cursor.fetchone()
        if not result:
            raise HTTPException(status_code=404, detail="Chapter not found")
        
        chapter_id = result['id']
        
        # Get segments with timing data and audio URLs
        cursor.execute('''
            SELECT segment_index, text, timing_data, audio_url, status
            FROM segments
            WHERE chapter_id = ?
            ORDER BY segment_index ASC
        ''', (chapter_id,))
        
        segments = cursor.fetchall()
        
        if not segments:
            raise HTTPException(
                status_code=404,
                detail="No segments found. Generate audio first."
            )
        
        # Build response from DB segments
        chunks = []
        total_duration = 0.0
        
        for seg in segments:
            timing = json.loads(seg['timing_data']) if seg['timing_data'] else {}
            
            chunk_data = {
                "index": seg['segment_index'],
                "text": seg['text'],
                "start": timing.get('start', 0.0),
                "end": timing.get('end', 0.0),
                "duration": timing.get('duration', 0.0),
                "audio_url": seg['audio_url'],
                "status": seg['status']
            }
            chunks.append(chunk_data)
            total_duration = max(total_duration, chunk_data['end'])
        
        return {
            "novel_slug": novel_slug,
            "chapter_number": chapter_number,
            "total_duration": round(total_duration, 3),
            "chunk_count": len(chunks),
            "chunks": chunks,
            "source": "database"
        }


@router.post("/generate/{novel_slug}/{chapter_number}")
async def generate_chapter_audio(
    novel_slug: str, 
    chapter_number: int, 
    voice: str = "af_heart",
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Generate audio for a chapter using external TTS service."""
    
    job_key = f"{novel_slug}_{chapter_number}"
    
    # Check if already generating
    if tts_jobs.get(job_key, {}).get("status") == "generating":
        return {"status": "already_generating", "message": "Audio generation in progress"}
    
    # Get chapter from database
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.id, c.content, c.content_path
            FROM chapters c
            JOIN novels n ON c.novel_id = n.id
            WHERE n.slug = ? AND c.chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        chapter = cursor.fetchone()
        
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found in database")
        
        chapter_id = chapter['id']
        content = chapter['content']
        
        # Fallback to file if content not in DB
        if not content and chapter['content_path']:
            chapter_file = Path(chapter['content_path'])
            if chapter_file.exists():
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    content = '\n'.join(lines[3:]) if len(lines) > 3 else '\n'.join(lines)
        
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="Chapter content is empty")
        
        # Check if segments already exist and are ready
        cursor.execute('''
            SELECT COUNT(*) as count 
            FROM segments 
            WHERE chapter_id = ? AND status = 'ready'
        ''', (chapter_id,))
        
        existing = cursor.fetchone()
        if existing['count'] > 0:
            return {
                "status": "exists", 
                "message": "Audio already generated",
                "segments": existing['count']
            }
    
    # Queue TTS generation
    tts_jobs[job_key] = {"status": "generating", "progress": 0}
    
    background_tasks.add_task(
        run_tts_generation, 
        novel_slug, 
        chapter_number,
        chapter_id,
        content, 
        voice,
        job_key
    )
    
    return {
        "status": "queued",
        "message": f"Audio generation started for {novel_slug} chapter {chapter_number}",
        "voice": voice
    }


async def run_tts_generation(
    novel_slug: str, 
    chapter_number: int,
    chapter_id: int,
    text: str, 
    voice: str, 
    job_key: str
):
    """
    Background task to generate TTS audio via external service.
    
    Flow:
    1. Split text into chunks (orchestration stays here)
    2. For each chunk:
       a. Insert segment with 'processing' status
       b. Call TTS service (text → audio → R2 → URL)
       c. Update segment with audio_url and timing
    3. Track progress in tts_jobs dict
    """
    import asyncio
    
    try:
        # Split text into chunks (chunking logic stays in Render)
        chunks = split_text_into_chunks(text, max_length=500)
        logger.info(f"Processing {novel_slug} Ch.{chapter_number}: {len(chunks)} chunks")
        
        if not chunks:
            raise ValueError("No chunks to process")
        
        # Clear existing segments for this chapter
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM segments WHERE chapter_id = ?', (chapter_id,))
            conn.commit()
        
        # Process each chunk
        current_time = 0.0
        silence_duration = 0.5  # Gap between segments
        
        for idx, chunk in enumerate(chunks):
            tts_jobs[job_key] = {
                "status": "generating", 
                "progress": int((idx / len(chunks)) * 100)
            }
            
            # Create unique segment ID (opaque to TTS service)
            segment_id = f"{novel_slug}_ch{chapter_number}_seg{idx:04d}"
            
            # Insert segment with 'processing' status
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO segments (chapter_id, segment_index, text, status, created_at)
                    VALUES (?, ?, ?, 'processing', ?)
                ''', (chapter_id, idx, chunk.strip(), datetime.utcnow()))
                db_segment_id = cursor.lastrowid
                conn.commit()
            
            try:
                logger.info(f"  Generating chunk {idx + 1}/{len(chunks)}: {chunk[:50]}...")
                
                # Call TTS service
                result = await call_tts_service(chunk, voice, segment_id)
                
                # Update segment with timing and audio URL
                duration = result.get('duration', 0.0)
                timing_data = {
                    "start": round(current_time, 3),
                    "end": round(current_time + duration, 3),
                    "duration": round(duration, 3)
                }
                
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE segments 
                        SET audio_url = ?, timing_data = ?, status = 'ready', last_accessed = ?
                        WHERE id = ?
                    ''', (result['audio_url'], json.dumps(timing_data), datetime.utcnow(), db_segment_id))
                    conn.commit()
                
                current_time += duration + silence_duration
                logger.info(f"    ✓ Chunk {idx + 1} ready - {duration:.2f}s → {result['audio_url']}")
                
            except (TTSUnavailableError, TTSTimeoutError) as e:
                # Mark segment as failed, continue with next
                logger.error(f"    ✗ Chunk {idx + 1} failed: {e}")
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE segments SET status = 'failed' WHERE id = ?
                    ''', (db_segment_id,))
                    conn.commit()
                    
            except HTTPException as e:
                # 4xx error (invalid request) - mark failed, don't retry
                logger.error(f"    ✗ Chunk {idx + 1} invalid: {e.detail}")
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE segments SET status = 'failed' WHERE id = ?
                    ''', (db_segment_id,))
                    conn.commit()
        
        # Count results
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) as ready,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM segments WHERE chapter_id = ?
            ''', (chapter_id,))
            stats = cursor.fetchone()
        
        tts_jobs[job_key] = {
            "status": "complete", 
            "progress": 100,
            "ready_segments": stats['ready'],
            "failed_segments": stats['failed']
        }
        logger.info(f"✓✓ Generation complete: {stats['ready']} ready, {stats['failed']} failed")
            
    except Exception as e:
        logger.error(f"❌ TTS generation failed: {e}", exc_info=True)
        tts_jobs[job_key] = {"status": "failed", "error": str(e)}
        
        # Mark all processing segments as failed
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE segments SET status = 'failed' 
                WHERE chapter_id = ? AND status = 'processing'
            ''', (chapter_id,))
            conn.commit()


def split_text_into_chunks(text: str, max_length: int = 500) -> list:
    """
    Split text into chunks for TTS processing.
    Chunking is a product decision, not a model decision - stays in Render.
    """
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
                sentence = sentence.strip()
                if not sentence:
                    continue
                    
                if len(current_chunk) + len(sentence) + 1 <= max_length:
                    current_chunk = (current_chunk + " " + sentence).strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk)
    
    # Fallback if no chunks were created
    if not chunks and text.strip():
        words = text.split()
        current_chunk = ""
        for word in words:
            if len(current_chunk) + len(word) + 1 <= max_length:
                current_chunk = (current_chunk + " " + word).strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = word
        if current_chunk:
            chunks.append(current_chunk)
    
    return chunks