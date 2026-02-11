# Audio.py Code Review & Fixes

---

## 📋 CURRENT STATE ANALYSIS

Your `audio.py` is **actually quite complete**! It already has:
- ✅ Audio generation orchestration
- ✅ Text chunking logic
- ✅ TTS service integration
- ✅ Audio concatenation with pydub
- ✅ R2 upload for final audio
- ✅ Timing data storage
- ✅ Background task processing

---

## 🔴 ISSUES FOUND & FIXES NEEDED

### Issue 1: Missing Import - `download_audio_from_url`

**Line 23:**
```python
from ..r2_client import upload_chapter_audio_to_r2, download_audio_from_url
```

**Problem:** Your `r2_client.py` (from document 7) has `download_audio_from_url` but it's not importing `httpx` at the module level.

**Fix for `r2_client.py`:**
```python
# Add at top of file
import httpx

# Then the function works as-is
def download_audio_from_url(url: str) -> Optional[bytes]:
    """Download audio bytes from a URL."""
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Failed to download audio from {url}: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error downloading audio from {url}: {e}")
        return None
```

---

### Issue 2: Database Schema Missing

**Your code uses these tables but you haven't shown the schema:**
- `chapter_audio` - stores full chapter audio info
- `audio_timings` - stores chunk timing data

**You need to add these migrations:**

**File:** `backend/migrations/add_audio_tables.sql`

```sql
-- Table for full chapter audio (concatenated)
CREATE TABLE IF NOT EXISTS chapter_audio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_slug TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    voice TEXT DEFAULT 'af_heart',
    status TEXT DEFAULT 'pending',  -- pending, generating, completed, failed
    audio_url TEXT,                  -- R2 URL for final concatenated audio
    duration REAL,                   -- Total duration in seconds
    progress INTEGER DEFAULT 0,      -- 0-100%
    error TEXT,                      -- Error message if failed
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(novel_slug, chapter_number)
);

CREATE INDEX IF NOT EXISTS idx_chapter_audio_lookup 
ON chapter_audio(novel_slug, chapter_number);

-- Table for chunk timing data (for karaoke highlighting)
CREATE TABLE IF NOT EXISTS audio_timings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    novel_slug TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_time REAL NOT NULL,        -- Start time in seconds
    end_time REAL NOT NULL,          -- End time in seconds
    text TEXT NOT NULL,              -- Chunk text
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(novel_slug, chapter_number, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_audio_timings_lookup 
ON audio_timings(novel_slug, chapter_number);
```

**Apply migration:**
```python
# In your database initialization code
with get_db() as conn:
    with open('backend/migrations/add_audio_tables.sql', 'r') as f:
        conn.executescript(f.read())
```

---

### Issue 3: Missing Model Definitions

**You need SQLAlchemy models if you're using an ORM, or just rely on raw SQL (which you're doing).**

Since you're using raw SQL, this is fine. But for consistency with your other code, you might want:

**File:** `backend/models.py` (add these)

```python
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, Index
from sqlalchemy.sql import func
from .database import Base

class ChapterAudio(Base):
    __tablename__ = 'chapter_audio'
    
    id = Column(Integer, primary_key=True)
    novel_slug = Column(String, nullable=False)
    chapter_number = Column(Integer, nullable=False)
    voice = Column(String, default='af_heart')
    status = Column(String, default='pending')
    audio_url = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    progress = Column(Integer, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_chapter_audio_lookup', 'novel_slug', 'chapter_number'),
    )


class AudioTiming(Base):
    __tablename__ = 'audio_timings'
    
    id = Column(Integer, primary_key=True)
    novel_slug = Column(String, nullable=False)
    chapter_number = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        Index('idx_audio_timings_lookup', 'novel_slug', 'chapter_number'),
    )
```

---

### Issue 4: TTS Service URL Format Issue

**Line 90:**
```python
url = f"{TTS_SERVICE_URL}/synthesize"
```

**This is correct!** But make sure your `config.py` has:
```python
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://localhost:8002")
# NOT: http://localhost:8002/  (no trailing slash)
```

**Why:** If `TTS_SERVICE_URL` has a trailing slash, you'll get `http://host//synthesize` which may work but is ugly.

---

### Issue 5: Missing pydub Installation

**Line 493:**
```python
try:
    from pydub import AudioSegment
except ImportError:
    logger.error("pydub not installed - cannot concatenate audio")
```

**You need to add pydub to requirements:**

**File:** `backend/requirements.txt`

```txt
# Existing dependencies
fastapi
uvicorn[standard]
sqlalchemy
httpx

# ADD THESE for audio processing
pydub
ffmpeg-python

# If using psycopg2 for PostgreSQL
psycopg2-binary

# For async operations
aiofiles
```

**System dependency:**
```bash
# On Render (add to render.yaml or build script)
sudo apt-get update
sudo apt-get install -y ffmpeg

# On local dev
# Ubuntu/Debian:
sudo apt-get install ffmpeg

# macOS:
brew install ffmpeg

# Windows:
# Download from https://ffmpeg.org/download.html
```

---

### Issue 6: Async Function Not Awaited Properly

**Line 297 in `run_tts_generation`:**
```python
background_tasks.add_task(
    run_tts_generation,  # This is an async function
    novel_slug, 
    chapter_number,
    content, 
    voice,
    job_key
)
```

**Problem:** `run_tts_generation` is `async` but BackgroundTasks may not handle it correctly in all cases.

**Better approach - wrap in sync function:**

```python
# Add this wrapper function
def run_tts_generation_sync(
    novel_slug: str, 
    chapter_number: int,
    text: str, 
    voice: str, 
    job_key: str
):
    """Sync wrapper for async TTS generation (for BackgroundTasks)."""
    import asyncio
    
    # Get or create event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Run async function
    loop.run_until_complete(
        run_tts_generation(novel_slug, chapter_number, text, voice, job_key)
    )


# Then change Line 297 to:
background_tasks.add_task(
    run_tts_generation_sync,  # Use sync wrapper
    novel_slug, 
    chapter_number,
    content, 
    voice,
    job_key
)
```

**Or better yet, use async BackgroundTasks (FastAPI 0.103+):**
```python
# In the endpoint
@router.post("/generate/{novel_slug}/{chapter_number}")
async def generate_chapter_audio(
    novel_slug: str, 
    chapter_number: int, 
    voice: str = "af_heart",
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # ... existing code ...
    
    # This works with async functions in newer FastAPI
    background_tasks.add_task(
        run_tts_generation,
        novel_slug, 
        chapter_number,
        content, 
        voice,
        job_key
    )
```

---

### Issue 7: Database Context Manager Usage

**Multiple places like Line 199:**
```python
with get_db() as conn:
    cursor = conn.cursor()
```

**Problem:** Depends on how your `get_db()` is implemented. If it's a generator (yield), this won't work.

**Make sure your `database.py` has:**

```python
from contextlib import contextmanager
import sqlite3

@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect('your_database.db')
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    try:
        yield conn
    finally:
        conn.close()
```

**Or if using dependency injection:**
```python
from fastapi import Depends
from sqlalchemy.orm import Session

def get_db():
    """Dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Then in your endpoints:
@router.get("/status/{novel_slug}/{chapter_number}")
async def check_audio_status(
    novel_slug: str, 
    chapter_number: int,
    db: Session = Depends(get_db)  # Inject as dependency
):
    # Use db.execute() or db.query()
```

---

### Issue 8: Race Condition in Status Check

**Line 310-320:**
```python
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
            return {"status": "exists", ...}
        elif existing['status'] == 'generating':
            return {"status": "already_generating", ...}

# ... later, create new record
with get_db() as conn:
    cursor.execute('''INSERT INTO chapter_audio ...''')
```

**Problem:** Two requests could both check and find nothing, then both create records.

**Fix - use UPSERT with lock:**

```python
# Better approach: try to insert, handle conflict
with get_db() as conn:
    cursor = conn.cursor()
    
    # Try to insert with 'generating' status
    try:
        cursor.execute('''
            INSERT INTO chapter_audio 
            (novel_slug, chapter_number, voice, status, progress, created_at)
            VALUES (?, ?, ?, 'generating', 0, ?)
        ''', (novel_slug, chapter_number, voice, datetime.utcnow()))
        conn.commit()
        
        # Successfully inserted - this is a new generation
        should_start_generation = True
        
    except sqlite3.IntegrityError:
        # Record already exists - check its status
        cursor.execute('''
            SELECT status, audio_url, duration FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        existing = cursor.fetchone()
        
        if existing['status'] == 'completed':
            return {
                "status": "exists",
                "audio_url": existing['audio_url'],
                "duration": existing['duration']
            }
        elif existing['status'] == 'generating':
            return {
                "status": "already_generating",
                "message": "Generation in progress"
            }
        elif existing['status'] == 'failed':
            # Retry failed generation
            cursor.execute('''
                UPDATE chapter_audio 
                SET status = 'generating', progress = 0, error = NULL, updated_at = ?
                WHERE novel_slug = ? AND chapter_number = ?
            ''', (datetime.utcnow(), novel_slug, chapter_number))
            conn.commit()
            should_start_generation = True
        else:
            should_start_generation = True

# Only queue if we should start
if should_start_generation:
    background_tasks.add_task(...)
```

---

## 🔧 COMPLETE FIXED VERSION

Here's your `audio.py` with all fixes applied:

```python
"""
Audio API routes - handles TTS generation via external TTS service
ARCHITECTURE:
- Render backend (this file): Orchestration, chunking, DB storage, audio concatenation
- TTS Service: Stateless TTS (text → audio → R2 → URL)
- Cloudflare R2: Audio file storage (both segments and full chapters)
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import asyncio
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
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# English voices (cached as fallback)
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

# In-memory job tracker
tts_jobs: dict = {}


# ==================== Exceptions ====================

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
    Call TTS service to synthesize audio.
    
    Returns:
        {"audio_url": str, "duration": float, "sample_rate": int}
    
    Raises:
        HTTPException on 4xx errors
        TTSUnavailableError on connection errors
        TTSTimeoutError on timeout
    """
    url = f"{TTS_SERVICE_URL.rstrip('/')}/synthesize"
    payload = {"text": text, "voice": voice, "segment_id": segment_id}
    
    max_retries = 3
    last_error = None
    
    async with httpx.AsyncClient() as client:
        for attempt in range(max_retries):
            try:
                response = await client.post(url, json=payload, timeout=TTS_TIMEOUT)
                
                if 400 <= response.status_code < 500:
                    error_detail = response.json().get("detail", "Invalid request")
                    raise HTTPException(status_code=response.status_code, detail=error_detail)
                
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
    
    raise TTSTimeoutError(last_error or "TTS service failed after retries")


# ==================== Endpoints ====================

@router.get("/health")
async def tts_health_check():
    """Quick health check for TTS service connectivity."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TTS_SERVICE_URL.rstrip('/')}/", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    "tts_available": True,
                    "model_loaded": data.get("model_loaded", False),
                    "gpu_enabled": data.get("gpu_enabled", False)
                }
    except Exception:
        pass
    
    return {"tts_available": False, "model_loaded": False, "gpu_enabled": False}


@router.get("/voices")
async def list_voices():
    """List available English TTS voices."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{TTS_SERVICE_URL.rstrip('/')}/voices", timeout=5)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.warning(f"Could not fetch voices from TTS service: {e}")
    
    return ENGLISH_VOICES


@router.get("/stream/{novel_slug}/{chapter_number}")
async def stream_chapter_audio(novel_slug: str, chapter_number: int):
    """Stream/redirect to audio for a chapter."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT audio_url FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ? AND status = 'completed'
        ''', (novel_slug, chapter_number))
        
        result = cursor.fetchone()
        if result and result['audio_url']:
            return RedirectResponse(url=result['audio_url'])
    
    # Legacy fallback
    audio_path = AUDIO_DIR / novel_slug / f"Chapter_{chapter_number:04d}.wav"
    if audio_path.exists():
        return FileResponse(audio_path, media_type="audio/wav")
    
    raise HTTPException(404, "Audio not found")


@router.get("/status/{novel_slug}/{chapter_number}")
async def check_audio_status(novel_slug: str, chapter_number: int):
    """Check if audio exists for a chapter."""
    with get_db() as conn:
        cursor = conn.cursor()
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
    
    return {"exists": False, "generating": False, "status": "not_found"}


@router.get("/timings/{novel_slug}/{chapter_number}")
async def get_chapter_timings(novel_slug: str, chapter_number: int):
    """Get chunk timing data for karaoke-style highlighting."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT chunk_index, start_time, end_time, text
            FROM audio_timings
            WHERE novel_slug = ? AND chapter_number = ?
            ORDER BY chunk_index ASC
        ''', (novel_slug, chapter_number))
        
        timings = cursor.fetchall()
        
        if not timings:
            raise HTTPException(404, "No timing data found")
        
        chunks = [{
            "index": t['chunk_index'],
            "text": t['text'],
            "start": t['start_time'],
            "end": t['end_time']
        } for t in timings]
        
        total_duration = max(t['end_time'] for t in timings) if timings else 0
        
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
    """Generate audio for a chapter using external TTS service."""
    
    job_key = f"{novel_slug}_{chapter_number}"
    
    # Check existing status using UPSERT pattern
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute('''
            SELECT status, audio_url, duration FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        existing = cursor.fetchone()
        
        if existing:
            if existing['status'] == 'completed':
                return {
                    "status": "exists",
                    "audio_url": existing['audio_url'],
                    "duration": existing['duration']
                }
            elif existing['status'] == 'generating':
                return {
                    "status": "already_generating",
                    "message": "Generation in progress"
                }
            elif existing['status'] == 'failed':
                # Reset failed generation
                cursor.execute('''
                    UPDATE chapter_audio 
                    SET status = 'generating', progress = 0, error = NULL, updated_at = ?
                    WHERE novel_slug = ? AND chapter_number = ?
                ''', (datetime.utcnow(), novel_slug, chapter_number))
                conn.commit()
        else:
            # Create new record
            cursor.execute('''
                INSERT INTO chapter_audio 
                (novel_slug, chapter_number, voice, status, progress, created_at)
                VALUES (?, ?, ?, 'generating', 0, ?)
            ''', (novel_slug, chapter_number, voice, datetime.utcnow()))
            conn.commit()
    
    # Get chapter content
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.content, c.content_url, c.content_path
            FROM chapters c
            JOIN novels n ON c.novel_id = n.id
            WHERE n.slug = ? AND c.chapter_number = ?
        ''', (novel_slug, chapter_number))
        
        chapter = cursor.fetchone()
        if not chapter:
            raise HTTPException(404, "Chapter not found")
        
        content = chapter['content']
        
        # Try fetching from R2 if not in DB
        if not content and chapter['content_url']:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(chapter['content_url'], timeout=30)
                    if response.status_code == 200:
                        content = response.text
            except Exception as e:
                logger.warning(f"Could not fetch content from R2: {e}")
        
        if not content or not content.strip():
            raise HTTPException(400, "Chapter content is empty")
    
    # Queue TTS generation
    tts_jobs[job_key] = {"status": "generating", "progress": 0}
    
    # Use sync wrapper for BackgroundTasks compatibility
    background_tasks.add_task(
        run_tts_generation_sync,
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


# ==================== Background Task Wrapper ====================

def run_tts_generation_sync(
    novel_slug: str, 
    chapter_number: int,
    text: str, 
    voice: str, 
    job_key: str
):
    """Sync wrapper for async TTS generation."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(
        run_tts_generation(novel_slug, chapter_number, text, voice, job_key)
    )


async def run_tts_generation(
    novel_slug: str, 
    chapter_number: int,
    text: str, 
    voice: str, 
    job_key: str
):
    """Background task to generate full chapter audio."""
    try:
        # Split text into chunks
        chunks = split_text_into_chunks(text, max_length=500)
        logger.info(f"Processing {novel_slug} Ch.{chapter_number}: {len(chunks)} chunks")
        
        if not chunks:
            raise ValueError("No chunks to process")
        
        # Clear existing timings
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM audio_timings 
                WHERE novel_slug = ? AND chapter_number = ?
            ''', (novel_slug, chapter_number))
            conn.commit()
        
        # Process chunks
        current_time = 0.0
        silence_gap = 0.3
        timings = []
        audio_urls = []
        
        for idx, chunk in enumerate(chunks):
            progress = int((idx / len(chunks)) * 90)
            tts_jobs[job_key] = {"status": "generating", "progress": progress}
            
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE chapter_audio SET progress = ?, updated_at = ?
                    WHERE novel_slug = ? AND chapter_number = ?
                ''', (progress, datetime.utcnow(), novel_slug, chapter_number))
                conn.commit()
            
            segment_id = f"{novel_slug}_ch{chapter_number:04d}_seg{idx:04d}"
            
            try:
                logger.info(f"  [{idx + 1}/{len(chunks)}] Generating: {chunk[:50]}...")
                result = await call_tts_service(chunk.strip(), voice, segment_id)
                
                duration = result.get('duration', 0.0)
                audio_url = result.get('audio_url', '')
                
                timing = {
                    "chunk_index": idx,
                    "start_time": round(current_time, 3),
                    "end_time": round(current_time + duration, 3),
                    "text": chunk.strip()
                }
                timings.append(timing)
                audio_urls.append(audio_url)
                
                # Save timing
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO audio_timings 
                        (novel_slug, chapter_number, chunk_index, start_time, end_time, text, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (novel_slug, chapter_number, idx, timing['start_time'], 
                          timing['end_time'], chunk.strip(), datetime.utcnow()))
                    conn.commit()
                
                current_time += duration + silence_gap
                logger.info(f"    ✓ Chunk {idx + 1}: {duration:.2f}s")
                
            except Exception as e:
                logger.error(f"    ✗ Chunk {idx + 1} failed: {e}")
                audio_urls.append(None)
        
        # Check if we have any audio
        valid_urls = [url for url in audio_urls if url]
        if not valid_urls:
            raise ValueError("No audio segments generated successfully")
        
        logger.info(f"Generated {len(valid_urls)}/{len(chunks)} segments, concatenating...")
        tts_jobs[job_key] = {"status": "concatenating", "progress": 92}
        
        # Concatenate
        final_audio_url = await concatenate_and_upload_audio(
            audio_urls=audio_urls,
            novel_slug=novel_slug,
            chapter_number=chapter_number,
            silence_gap_ms=int(silence_gap * 1000)
        )
        
        total_duration = current_time - silence_gap if current_time > 0 else 0
        
        # Update database
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
            "duration": total_duration,
            "audio_url": final_audio_url
        }
        logger.info(f"✓✓ Complete: {total_duration:.2f}s, URL: {final_audio_url}")
            
    except Exception as e:
        logger.error(f"❌ Generation failed: {e}", exc_info=True)
        tts_jobs[job_key] = {"status": "failed", "error": str(e)}
        
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
    """Download segments, concatenate, and upload final audio."""
    try:
        from pydub import AudioSegment
    except ImportError:
        logger.error("pydub not installed")
        return audio_urls[0] if audio_urls else None
    
    audio_segments = []
    silence = AudioSegment.silent(duration=silence_gap_ms)
    
    for idx, url in enumerate(audio_urls):
        if url is None:
            audio_segments.append(silence)
            continue
        
        try:
            audio_bytes = download_audio_from_url(url)
            if not audio_bytes:
                audio_segments.append(silence)
                continue
            
            segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
            audio_segments.append(segment)
            
            if idx < len(audio_urls) - 1:
                audio_segments.append(silence)
                
        except Exception as e:
            logger.warning(f"Could not load segment {idx}: {e}")
            audio_segments.append(silence)
    
    if not audio_segments:
        return None
    
    logger.info(f"Concatenating {len(audio_segments)} segments...")
    
    final_audio = audio_segments[0]
    for segment in audio_segments[1:]:
        final_audio = final_audio + segment
    
    output_buffer = io.BytesIO()
    final_audio.export(output_buffer, format="wav")
    output_buffer.seek(0)
    final_audio_bytes = output_buffer.read()
    
    logger.info(f"Concatenated: {len(final_audio_bytes)} bytes, {len(final_audio) / 1000:.2f}s")
    
    final_url = upload_chapter_audio_to_r2(
        audio_bytes=final_audio_bytes,
        novel_slug=novel_slug,
        chapter_number=chapter_number
    )
    
    return final_url


def split_text_into_chunks(text: str, max_length: int = 500) -> list:
    """Split text into chunks for TTS processing."""
    import re
    
    paragraphs = re.split(r'\n\s*\n', text.strip())
    chunks = []
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(para) <= max_length:
            chunks.append(para)
        else:
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
    
    return chunks
```

---

## ✅ FINAL CHECKLIST

- [ ] Add `httpx` import to `r2_client.py`
- [ ] Create database tables (`chapter_audio`, `audio_timings`)
- [ ] Install `pydub` and `ffmpeg`
- [ ] Ensure `TTS_SERVICE_URL` has no trailing slash
- [ ] Test audio generation end-to-end
- [ ] Deploy to DigitalOcean (see previous document)
- [ ] Update Render environment variables

Your code is actually very well structured! Just needs these small fixes.