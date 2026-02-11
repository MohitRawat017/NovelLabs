"""
Audio API routes - handles TTS generation via external TTS service
Segments are stored per-chunk with audio_url pointing to R2 CDN

ARCHITECTURE:
- Render backend (this file): Orchestration, chunking, DB storage, audio concatenation
- Lightning AI: Stateless TTS (text → audio → R2 → URL)
- Cloudflare R2: Audio file storage (both segments and full chapters)
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import httpx
import io
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

# Import configuration
from ..config import TTS_SERVICE_URL, TTS_TIMEOUT

# Import database utilities
from ..database import get_db

# Import R2 client for uploading concatenated audio
from ..r2_client import upload_chapter_audio_to_r2, download_audio_from_url

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
    url = f"{TTS_SERVICE_URL.rstrip('/')}/synthesize"
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
                    try:
                        error_detail = response.json().get("detail", "Invalid request")
                    except Exception:
                        error_detail = f"TTS service error {response.status_code}"
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

@router.get("/wake")
async def wake_tts_service():
    """
    Wake up the Lightning AI TTS service.
    
    Call this endpoint to ensure TTS service is awake before generating audio.
    Lightning AI studios sleep after 10 min of inactivity.
    
    Returns the TTS service status.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TTS_SERVICE_URL}/", timeout=60)  # Long timeout for cold start
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "awake",
                    "tts_service": TTS_SERVICE_URL,
                    "model_loaded": data.get("model_loaded", False),
                    "gpu_available": data.get("gpu_available", False)
                }
            else:
                return {
                    "status": "error",
                    "tts_service": TTS_SERVICE_URL,
                    "error": f"TTS service returned {response.status_code}"
                }
    except httpx.ConnectError:
        return {
            "status": "sleeping",
            "tts_service": TTS_SERVICE_URL,
            "error": "TTS service not reachable (may be sleeping)",
            "hint": "Try again in 30-60 seconds"
        }
    except httpx.ReadTimeout:
        return {
            "status": "waking",
            "tts_service": TTS_SERVICE_URL,
            "message": "TTS service is waking up, model loading...",
            "hint": "Try again in 30-60 seconds"
        }
    except Exception as e:
        return {
            "status": "error",
            "tts_service": TTS_SERVICE_URL,
            "error": str(e)
        }


@router.get("/health")
async def tts_health_check():
    """Quick health check for TTS service connectivity."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TTS_SERVICE_URL}/", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    "tts_available": True,
                    "model_loaded": data.get("model_loaded", False),
                    "gpu_enabled": data.get("gpu_enabled", False)
                }
    except Exception:
        pass
    
    return {
        "tts_available": False,
        "model_loaded": False,
        "gpu_enabled": False
    }


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
    
    Checks chapter_audio table for full chapter audio URL.
    Falls back to local filesystem for legacy files.
    """
    # Check for full chapter audio in database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT audio_url FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ? AND status = 'completed'
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
    """Check if audio exists for a chapter."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check chapter_audio table for full chapter audio
        cursor.execute('''
            SELECT status, audio_url, duration, progress, error
            FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        result = cursor.fetchone()
        
        if result:
            status = result['status']
            return {
                "exists": status == 'completed',
                "generating": status == 'generating',
                "status": status,
                "audio_url": result['audio_url'] if status == 'completed' else None,
                "duration": result['duration'],
                "progress": result['progress'] or 0,
                "error": result['error']
            }
    
    # Check filesystem as fallback
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    
    # Check in-memory job status
    job_key = f"{novel_slug}_{chapter_number}"
    job = tts_jobs.get(job_key, {})
    
    return {
        "exists": audio_path.exists(),
        "generating": job.get("status") == "generating",
        "status": "completed" if audio_path.exists() else ("generating" if job.get("status") == "generating" else "not_found"),
        "audio_url": None,
        "duration": None,
        "progress": job.get("progress", 0),
        "error": job.get("error")
    }


@router.get("/timings/{novel_slug}/{chapter_number}")
async def get_chapter_timings(novel_slug: str, chapter_number: int):
    """Get chunk timing data for karaoke-style highlighting."""
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get timings from audio_timings table
        cursor.execute('''
            SELECT chunk_index, start_time, end_time, text
            FROM audio_timings
            WHERE novel_slug = ? AND chapter_number = ?
            ORDER BY chunk_index ASC
        ''', (novel_slug, chapter_number))
        
        timings = cursor.fetchall()
        
        if not timings:
            # Check if audio exists but no timings
            cursor.execute('''
                SELECT status FROM chapter_audio
                WHERE novel_slug = ? AND chapter_number = ?
            ''', (novel_slug, chapter_number))
            
            audio_status = cursor.fetchone()
            if audio_status:
                raise HTTPException(
                    status_code=404,
                    detail=f"Audio status is '{audio_status['status']}' but no timing data found."
                )
            
            raise HTTPException(
                status_code=404,
                detail="No timing data found. Generate audio first."
            )
        
        # Build response
        chunks = []
        total_duration = 0.0
        
        for t in timings:
            chunk_data = {
                "index": t['chunk_index'],
                "text": t['text'],
                "start": t['start_time'],
                "end": t['end_time']
            }
            chunks.append(chunk_data)
            total_duration = max(total_duration, t['end_time'])
        
        return {
            "novel_slug": novel_slug,
            "chapter_number": chapter_number,
            "total_duration": round(total_duration, 3),
            "chunk_count": len(chunks),
            "chunks": chunks
        }


@router.post("/generate/{novel_slug}/{chapter_number}")
async def generate_chapter_audio(
    novel_slug: str, 
    chapter_number: int, 
    voice: str = "af_heart",
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Generate audio for a chapter using external TTS service.
    
    Flow:
    1. Check if audio already exists in chapter_audio table
    2. Get chapter content from database or R2
    3. Create chapter_audio record with 'generating' status
    4. Queue background task to generate audio
    """
    
    job_key = f"{novel_slug}_{chapter_number}"
    
    # Check if already exists or generating
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT status, audio_url, duration FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        existing = cursor.fetchone()
        
        if existing:
            if existing['status'] == 'completed':
                return {
                    "status": "exists", 
                    "message": "Audio already generated",
                    "audio_url": existing['audio_url'],
                    "duration": existing['duration']
                }
            elif existing['status'] == 'generating':
                return {
                    "status": "already_generating", 
                    "message": "Audio generation in progress"
                }
    
    # Get chapter content
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.id, c.content, c.content_path, c.content_url
            FROM chapters c
            JOIN novels n ON c.novel_id = n.id
            WHERE n.slug = ? AND c.chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        chapter = cursor.fetchone()
        
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found in database")
        
        chapter_id = chapter['id']
        content = chapter['content']
        
        # Try to get content from R2 if not in DB
        if not content and chapter['content_url']:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(chapter['content_url'], timeout=30)
                    if response.status_code == 200:
                        content = response.text
            except Exception as e:
                logger.warning(f"Could not fetch content from R2: {e}")
        
        # Fallback to file if content not in DB
        if not content and chapter['content_path']:
            chapter_file = Path(chapter['content_path'])
            if chapter_file.exists():
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    content = '\n'.join(lines[3:]) if len(lines) > 3 else '\n'.join(lines)
        
        if not content or not content.strip():
            raise HTTPException(status_code=400, detail="Chapter content is empty")
    
    # Create or update chapter_audio record
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chapter_audio (novel_slug, chapter_number, voice, status, progress, created_at)
            VALUES (?, ?, ?, 'generating', 0, ?)
            ON CONFLICT (novel_slug, chapter_number) 
            DO UPDATE SET status = 'generating', voice = ?, progress = 0, error = NULL, updated_at = ?
        ''', (novel_slug, chapter_number, voice, datetime.utcnow(), voice, datetime.utcnow()))
        conn.commit()
    
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


async def run_tts_generation(
    novel_slug: str, 
    chapter_number: int,
    text: str, 
    voice: str, 
    job_key: str
):
    """
    Background task to generate full chapter audio via TTS service.
    
    Flow:
    1. Split text into chunks
    2. For each chunk, call TTS service to get audio segment
    3. Download each audio segment from R2
    4. Concatenate all audio into single WAV file using pydub
    5. Upload final concatenated audio to R2
    6. Save timing data to database
    7. Optionally clean up individual segment files
    """
    try:
        # Split text into chunks
        chunks = split_text_into_chunks(text, max_length=500)
        logger.info(f"Processing {novel_slug} Ch.{chapter_number}: {len(chunks)} chunks")
        
        if not chunks:
            raise ValueError("No chunks to process")
        
        # Clear existing timings for this chapter
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM audio_timings 
                WHERE novel_slug = ? AND chapter_number = ?
            ''', (novel_slug, chapter_number))
            conn.commit()
        
        # Process each chunk - collect audio URLs and timing data
        current_time = 0.0
        silence_gap = 0.3  # Gap between chunks in seconds
        timings = []
        audio_urls = []
        failed_chunks = []
        
        for idx, chunk in enumerate(chunks):
            progress = int((idx / len(chunks)) * 90)  # Reserve 10% for concatenation
            tts_jobs[job_key] = {"status": "generating", "progress": progress}
            
            # Update progress in database
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE chapter_audio SET progress = ?, updated_at = ?
                    WHERE novel_slug = ? AND chapter_number = ?
                ''', (progress, datetime.utcnow(), novel_slug, chapter_number))
                conn.commit()
            
            # Create unique segment ID
            segment_id = f"{novel_slug}_ch{chapter_number}_seg{idx:04d}"
            
            try:
                logger.info(f"  [{idx + 1}/{len(chunks)}] Generating: {chunk[:50]}...")
                
                # Call TTS service
                result = await call_tts_service(chunk.strip(), voice, segment_id)
                
                duration = result.get('duration', 0.0)
                audio_url = result.get('audio_url', '')
                
                # Record timing
                timing = {
                    "chunk_index": idx,
                    "start_time": round(current_time, 3),
                    "end_time": round(current_time + duration, 3),
                    "text": chunk.strip()
                }
                timings.append(timing)
                audio_urls.append(audio_url)
                
                # Save timing to database
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO audio_timings (novel_slug, chapter_number, chunk_index, start_time, end_time, text, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (novel_slug, chapter_number, idx, timing['start_time'], timing['end_time'], chunk.strip(), datetime.utcnow()))
                    conn.commit()
                
                current_time += duration + silence_gap
                logger.info(f"    ✓ Chunk {idx + 1}: {duration:.2f}s")
                
            except (TTSUnavailableError, TTSTimeoutError) as e:
                logger.error(f"    ✗ Chunk {idx + 1} failed: {e}")
                failed_chunks.append(idx)
                audio_urls.append(None)
                
            except HTTPException as e:
                logger.error(f"    ✗ Chunk {idx + 1} invalid: {e.detail}")
                failed_chunks.append(idx)
                audio_urls.append(None)
        
        # Check if we have enough audio to proceed
        valid_urls = [url for url in audio_urls if url]
        if not valid_urls:
            raise ValueError("No audio segments generated successfully")
        
        logger.info(f"Generated {len(valid_urls)}/{len(chunks)} segments, now concatenating...")
        tts_jobs[job_key] = {"status": "concatenating", "progress": 92}
        
        # Concatenate audio segments
        final_audio_url = await concatenate_and_upload_audio(
            audio_urls=audio_urls,
            novel_slug=novel_slug,
            chapter_number=chapter_number,
            silence_gap_ms=int(silence_gap * 1000)
        )
        
        total_duration = current_time - silence_gap if current_time > 0 else 0
        
        # Update chapter_audio record
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE chapter_audio 
                SET status = 'completed', audio_url = ?, duration = ?, progress = 100, updated_at = ?
                WHERE novel_slug = ? AND chapter_number = ?
            ''', (final_audio_url, total_duration, datetime.utcnow(), novel_slug, chapter_number))
            conn.commit()
        
        tts_jobs[job_key] = {
            "status": "complete", 
            "progress": 100,
            "chunks": len(chunks),
            "failed_chunks": len(failed_chunks),
            "duration": total_duration,
            "audio_url": final_audio_url
        }
        logger.info(f"✓✓ Generation complete: {len(timings)} chunks, {total_duration:.2f}s, URL: {final_audio_url}")
            
    except Exception as e:
        logger.error(f"❌ TTS generation failed: {e}", exc_info=True)
        tts_jobs[job_key] = {"status": "failed", "error": str(e)}
        
        # Update chapter_audio record with error
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE chapter_audio 
                SET status = 'failed', error = ?, updated_at = ?
                WHERE novel_slug = ? AND chapter_number = ?
            ''', (str(e), datetime.utcnow(), novel_slug, chapter_number))
            conn.commit()


async def concatenate_and_upload_audio(
    audio_urls: List[Optional[str]],
    novel_slug: str,
    chapter_number: int,
    silence_gap_ms: int = 300
) -> Optional[str]:
    """
    Download audio segments, concatenate them, and upload the final audio to R2.
    
    Args:
        audio_urls: List of R2 URLs for each segment (None for failed segments)
        novel_slug: Novel identifier
        chapter_number: Chapter number
        silence_gap_ms: Gap between segments in milliseconds
    
    Returns:
        URL of the uploaded concatenated audio, or None if failed
    """
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.error("pydub not installed - cannot concatenate audio")
        # Fallback: return first valid URL
        for url in audio_urls:
            if url:
                return url
        return None
    
    audio_segments = []

    # Create silence segment for gaps
    silence = AudioSegment.silent(duration=silence_gap_ms)

    for idx, url in enumerate(audio_urls):
        # Add silence gap between segments (not before the first one)
        if idx > 0:
            audio_segments.append(silence)

        if url is None:
            # Skip failed segments, add silence as placeholder
            audio_segments.append(silence)
            continue

        try:
            # Download audio bytes
            audio_bytes = download_audio_from_url(url)
            if audio_bytes is None:
                logger.warning(f"Could not download segment {idx}, adding silence")
                audio_segments.append(silence)
                continue

            # Load as AudioSegment
            segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
            audio_segments.append(segment)

        except Exception as e:
            logger.warning(f"Could not load segment {idx}: {e}, adding silence")
            audio_segments.append(silence)
    
    if not audio_segments:
        logger.error("No audio segments to concatenate")
        return None
    
    # Concatenate all segments
    logger.info(f"Concatenating {len(audio_segments)} segments...")
    
    final_audio = audio_segments[0]
    for segment in audio_segments[1:]:
        final_audio = final_audio + segment
    
    # Export to bytes
    output_buffer = io.BytesIO()
    final_audio.export(output_buffer, format="wav")
    output_buffer.seek(0)
    final_audio_bytes = output_buffer.read()
    
    logger.info(f"Concatenated audio: {len(final_audio_bytes)} bytes, {len(final_audio) / 1000:.2f}s")
    
    # Upload to R2
    final_url = upload_chapter_audio_to_r2(
        audio_bytes=final_audio_bytes,
        novel_slug=novel_slug,
        chapter_number=chapter_number
    )
    
    return final_url


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