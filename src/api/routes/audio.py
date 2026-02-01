"""
Audio API routes - handles TTS generation and audio streaming using Kokoro TTS
NOW WITH DATABASE INTEGRATION for segments table
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import json
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_DIR = BASE_DIR / "audio"
SCRAPED_DIR = BASE_DIR / "data" / "output"

# Ensure audio directory exists
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Import database utilities
from ..database import get_db

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
    """Check if audio exists for a chapter - checks both DB and filesystem"""
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
                   SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) as ready_count
            FROM segments
            WHERE chapter_id = ?
        ''', (chapter_id,))
        
        segment_stats = cursor.fetchone()
        has_segments = segment_stats['total'] > 0
        all_ready = segment_stats['total'] == segment_stats['ready_count'] if has_segments else False
    
    # Check filesystem as fallback
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    timing_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}_timing.json"
    
    job_key = f"{novel_slug}_{chapter_number}"
    job = tts_jobs.get(job_key, {})
    
    return {
        "exists": all_ready or audio_path.exists(),
        "segments_in_db": has_segments,
        "segments_ready": all_ready,
        "audio_file_exists": audio_path.exists(),
        "timing_file_exists": timing_path.exists(),
        "generating": job.get("status") == "generating",
        "progress": job.get("progress", 0),
        "error": job.get("error")
    }


@router.get("/timings/{novel_slug}/{chapter_number}")
async def get_chapter_timings(novel_slug: str, chapter_number: int):
    """Get chunk timing data for karaoke-style highlighting - NOW FROM DATABASE"""
    
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
        
        # Get segments with timing data
        cursor.execute('''
            SELECT segment_index, text, timing_data, status
            FROM segments
            WHERE chapter_id = ?
            ORDER BY segment_index ASC
        ''', (chapter_id,))
        
        segments = cursor.fetchall()
        
        if not segments:
            # Fallback to JSON file if DB not populated yet
            logger.warning(f"No segments in DB for chapter {chapter_number}, falling back to JSON")
            timing_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}_timing.json"
            
            if not timing_path.exists():
                raise HTTPException(
                    status_code=404,
                    detail="Timing data not found in DB or filesystem."
                )
            
            try:
                with open(timing_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading timing file: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
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
                "duration": timing.get('duration', 0.0)
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
    """Generate audio for a chapter using Kokoro TTS - SAVES TO DATABASE"""
    
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
        
        # Check if segments already exist
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


def run_tts_generation(
    novel_slug: str, 
    chapter_number: int,
    chapter_id: int,
    text: str, 
    voice: str, 
    job_key: str
):
    """Background task to generate TTS audio - SAVES TO DATABASE"""
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
        timing_file = output_dir / f"Chapter_{chapter_number:04d}_timing.json"
        
        # Initialize generator
        logger.info(f"Initializing TTS generator with voice: {voice}")
        generator = AudioBookGenerator(voice=voice, output_dir=str(AUDIO_DIR), use_gpu=True)
        
        # Split text into chunks
        chunks = split_text_into_chunks(text, max_length=500)
        logger.info(f"Processing {novel_slug} Ch.{chapter_number}: {len(chunks)} chunks")
        
        if not chunks:
            raise ValueError("No chunks to process")
        
        # Clear existing segments for this chapter
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM segments WHERE chapter_id = ?', (chapter_id,))
            conn.commit()
        
        # Generate audio for each chunk and save to database
        audio_segments = []
        current_time = 0.0
        silence_duration = 0.5
        sample_rate = 24000
        
        for idx, chunk in enumerate(chunks):
            tts_jobs[job_key] = {
                "status": "generating", 
                "progress": int((idx / len(chunks)) * 100)
            }
            
            # Insert segment with 'processing' status
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO segments (chapter_id, segment_index, text, status, created_at)
                    VALUES (?, ?, ?, 'processing', ?)
                ''', (chapter_id, idx, chunk.strip(), datetime.utcnow()))
                segment_id = cursor.lastrowid
                conn.commit()
            
            logger.info(f"  Generating chunk {idx + 1}/{len(chunks)}: {chunk[:50]}...")
            audio = generator._synthesize(chunk)
            
            if audio is not None and len(audio) > 0:
                segment_duration = len(audio) / sample_rate
                
                # Update segment with timing data
                timing_data = {
                    "start": round(current_time, 3),
                    "end": round(current_time + segment_duration, 3),
                    "duration": round(segment_duration, 3)
                }
                
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE segments 
                        SET timing_data = ?, status = 'ready', last_accessed = ?
                        WHERE id = ?
                    ''', (json.dumps(timing_data), datetime.utcnow(), segment_id))
                    conn.commit()
                
                audio_segments.append(audio)
                current_time += segment_duration + silence_duration
                logger.info(f"    ✓ Chunk {idx + 1} saved to DB - {segment_duration:.2f}s")
            else:
                # Mark segment as failed
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE segments SET status = 'failed' WHERE id = ?
                    ''', (segment_id,))
                    conn.commit()
                logger.warning(f"    ✗ Chunk {idx + 1} failed")
        
        if not audio_segments:
            raise ValueError("No audio segments were generated")
        
        # Combine segments with silence
        silence = np.zeros(int(sample_rate * silence_duration), dtype=np.float32)
        combined = []
        
        for i, seg in enumerate(audio_segments):
            combined.append(seg)
            if i < len(audio_segments) - 1:
                combined.append(silence)
        
        final_audio = np.concatenate(combined)
        
        # Save audio file (keep for backward compatibility)
        sf.write(str(output_file), final_audio, sample_rate)
        logger.info(f"✓ Audio file saved: {output_file}")
        
        # Also save JSON for backward compatibility
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT segment_index, text, timing_data 
                FROM segments 
                WHERE chapter_id = ? AND status = 'ready'
                ORDER BY segment_index
            ''', (chapter_id,))
            
            segments = cursor.fetchall()
            chunks_data = []
            for seg in segments:
                timing = json.loads(seg['timing_data'])
                chunks_data.append({
                    "index": seg['segment_index'],
                    "text": seg['text'],
                    **timing
                })
        
        timing_data_full = {
            "novel_slug": novel_slug,
            "chapter_number": chapter_number,
            "total_duration": round(len(final_audio) / sample_rate, 3),
            "chunk_count": len(chunks_data),
            "sample_rate": sample_rate,
            "silence_duration": silence_duration,
            "chunks": chunks_data
        }
        
        with open(timing_file, 'w', encoding='utf-8') as f:
            json.dump(timing_data_full, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✓ Timing file saved: {timing_file}")
        
        duration = len(final_audio) / sample_rate
        tts_jobs[job_key] = {
            "status": "complete", 
            "path": str(output_file),
            "progress": 100
        }
        logger.info(f"✓✓ Generation complete: {output_file} ({duration:.1f}s total)")
            
    except Exception as e:
        logger.error(f"❌ TTS generation failed: {e}", exc_info=True)
        tts_jobs[job_key] = {"status": "failed", "error": str(e)}
        
        # Mark all segments as failed
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE segments SET status = 'failed' 
                WHERE chapter_id = ? AND status = 'processing'
            ''', (chapter_id,))
            conn.commit()


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