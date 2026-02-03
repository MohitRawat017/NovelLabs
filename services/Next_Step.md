# TTS Integration Analysis & Recommendations
## NovelLabs - Lightning AI TTS + Chunk Highlighting

---

## 🎯 Your Requirements

1. **Audio chunks generated separately** and stored in R2
2. **Stream as one continuous audio** when playing
3. **Highlight current chunk** synchronized with audio playback
4. **Timing data** must be passed to frontend for karaoke effect

---

## 🔴 CRITICAL ISSUE IN CURRENT DESIGN

### The Problem: Segment-Based Storage Won't Work for Your Use Case

**Current TTS Service Design:**
```python
# Endpoint: POST /synthesize
{
    "text": "chunk text",
    "voice": "af_heart",
    "segment_id": "novel_slug_chapter_1_seg_0"
}
# Returns: { "audio_url": "https://r2.../seg_0.wav" }
```

**Why This Breaks Your App:**

1. ❌ **You have ~50-100 chunks per chapter**
   - 50 separate audio files in R2
   - 50 separate HTTP requests to play
   - Massive latency and buffering issues

2. ❌ **HTML5 Audio element can't seamlessly play multiple files**
   - You'd need to manually chain them
   - Gaps between chunks
   - Sync issues with highlighting

3. ❌ **No timing data for karaoke highlighting**
   - Each chunk is separate
   - No way to know when chunk 5 starts in the full audio
   - Can't sync highlighting

---

## ✅ RECOMMENDED ARCHITECTURE

### Option 1: Full Chapter Audio + Timing JSON (RECOMMENDED)

**How It Works:**
1. Backend **concatenates all chunks** into one audio file
2. Stores **one audio file** per chapter in R2
3. Stores **timing data** (chunk boundaries) separately
4. Frontend plays single audio + syncs highlights using timings

**Benefits:**
- ✅ Single audio file = smooth playback
- ✅ Standard HTML5 audio controls work
- ✅ Easy to implement chunk highlighting
- ✅ Efficient storage and bandwidth
- ✅ Matches your current AudioPlayer implementation

---

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Backend (Render/FastAPI)                                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. POST /api/audio/generate/{slug}/{chapter}                │
│     └─> Segment chapter text into chunks                     │
│     └─> For each chunk:                                      │
│         ├─> Call Lightning TTS: POST /synthesize             │
│         │   { text: chunk, voice: "af_heart",                │
│         │     segment_id: "novel_slug_ch1_seg_0" }           │
│         ├─> Get audio URL from R2                            │
│         ├─> Download audio bytes                             │
│         └─> Track timing: { start, end, text }               │
│     └─> Concatenate all audio chunks → final.wav             │
│     └─> Upload final.wav to R2                               │
│     └─> Save timing JSON to database                         │
│                                                               │
│  2. GET /api/audio/stream/{slug}/{chapter}                   │
│     └─> Return R2 URL for full chapter audio                 │
│                                                               │
│  3. GET /api/audio/timings/{slug}/{chapter}                  │
│     └─> Return timing JSON:                                  │
│         {                                                     │
│           "chunks": [                                         │
│             { "start": 0.0, "end": 2.5, "text": "..." },     │
│             { "start": 2.5, "end": 5.1, "text": "..." }      │
│           ]                                                   │
│         }                                                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Lightning AI TTS Service                                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  POST /synthesize                                             │
│  { text, voice, segment_id }                                 │
│  └─> Generate audio for single chunk                         │
│  └─> Upload to R2                                            │
│  └─> Return { audio_url, duration }                          │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Upload
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Cloudflare R2 Storage                                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Chunk files (temporary):                                    │
│  ├─ audio/novel_slug_ch1_seg_0.wav                           │
│  ├─ audio/novel_slug_ch1_seg_1.wav                           │
│  └─ ...                                                       │
│                                                               │
│  Final files (permanent):                                    │
│  └─ audio/novel_slug_chapter_1.wav  ← Frontend uses this     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ CDN URL
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Vercel/React)                                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  AudioPlayer Component:                                       │
│  └─> Load full chapter audio from R2                         │
│  └─> Fetch timing data from backend                          │
│  └─> On timeupdate event:                                    │
│      ├─> Find current chunk based on currentTime             │
│      └─> Highlight active chunk in UI                        │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 IMPLEMENTATION PLAN

### Step 1: Update Lightning TTS Service (Minor Changes)

**Keep existing endpoint as-is:**
```python
@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize_audio(request: SynthesizeRequest):
    # ... existing code ...
    # Returns: { audio_url, duration, sample_rate }
```

**Add helper endpoint (optional):**
```python
@app.post("/synthesize/bytes")
async def synthesize_audio_bytes(request: SynthesizeRequest):
    """
    Same as /synthesize but returns audio bytes directly (no R2 upload).
    Useful for backend-to-backend calls where you want to concatenate.
    """
    audio, duration = synthesize(request.text, request.voice)
    
    buffer = io.BytesIO()
    sf.write(buffer, audio, SAMPLE_RATE, format='WAV')
    buffer.seek(0)
    
    return Response(
        content=buffer.read(),
        media_type="audio/wav",
        headers={
            "X-Duration": str(duration),
            "X-Sample-Rate": str(SAMPLE_RATE)
        }
    )
```

---

### Step 2: Update Backend Audio Generation Logic

**Current (broken) approach:**
```python
# DON'T DO THIS
for chunk in chunks:
    response = requests.post(f"{TTS_SERVICE}/synthesize", json={
        "text": chunk.text,
        "voice": voice,
        "segment_id": f"{slug}_ch{chapter}_seg{idx}"
    })
    # Now what? You have 50 separate audio files...
```

**Correct approach:**
```python
import io
import wave
import requests
from pydub import AudioSegment

async def generate_chapter_audio(slug: str, chapter: int, voice: str = "af_heart"):
    """
    Generate full chapter audio with timing data.
    """
    # 1. Get chapter content and segment it
    chapter_data = get_chapter_content(slug, chapter)
    chunks = segment_text(chapter_data.content)  # Your segmentation function
    
    # 2. Generate audio for each chunk
    audio_segments = []
    timings = []
    current_time = 0.0
    
    for idx, chunk_text in enumerate(chunks):
        # Call TTS service
        tts_response = requests.post(
            f"{TTS_SERVICE_URL}/synthesize",
            json={
                "text": chunk_text,
                "voice": voice,
                "segment_id": f"{slug}_ch{chapter}_seg{idx}"
            },
            timeout=30
        )
        
        if not tts_response.ok:
            raise Exception(f"TTS failed for chunk {idx}")
        
        data = tts_response.json()
        audio_url = data["audio_url"]
        duration = data["duration"]
        
        # Download audio bytes from R2
        audio_response = requests.get(audio_url)
        audio_bytes = audio_response.content
        
        # Load as AudioSegment
        audio_segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
        audio_segments.append(audio_segment)
        
        # Record timing
        timings.append({
            "start": current_time,
            "end": current_time + duration,
            "text": chunk_text
        })
        
        current_time += duration
    
    # 3. Concatenate all audio segments
    final_audio = sum(audio_segments[1:], audio_segments[0])
    
    # 4. Export to bytes
    output_buffer = io.BytesIO()
    final_audio.export(output_buffer, format="wav")
    output_buffer.seek(0)
    final_audio_bytes = output_buffer.read()
    
    # 5. Upload final audio to R2
    final_filename = f"{slug}_chapter_{chapter}.wav"
    final_audio_url = upload_to_r2(final_audio_bytes, final_filename)
    
    # 6. Save timing data to database
    save_audio_timings(slug, chapter, timings)
    
    # 7. Clean up temporary chunk files (optional)
    # for idx in range(len(chunks)):
    #     delete_from_r2(f"{slug}_ch{chapter}_seg{idx}.wav")
    
    return {
        "audio_url": final_audio_url,
        "duration": current_time,
        "chunks": len(chunks)
    }
```

---

### Step 3: Backend API Endpoints

**File: `backend/routers/audio.py`**

```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
import requests

router = APIRouter(prefix="/audio", tags=["audio"])

TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://localhost:8002")

# ==================== Audio Status ====================

@router.get("/status/{slug}/{chapter}")
async def get_audio_status(slug: str, chapter: int):
    """
    Check if audio exists for a chapter.
    """
    # Check if final audio file exists in R2 or database
    audio_record = db.query(Audio).filter_by(
        novel_slug=slug,
        chapter_number=chapter
    ).first()
    
    if audio_record and audio_record.status == "completed":
        return {
            "exists": True,
            "generating": False,
            "url": audio_record.url,
            "duration": audio_record.duration
        }
    elif audio_record and audio_record.status == "generating":
        return {
            "exists": False,
            "generating": True,
            "progress": audio_record.progress  # Optional: track %
        }
    else:
        return {
            "exists": False,
            "generating": False
        }

# ==================== Audio Generation ====================

@router.post("/generate/{slug}/{chapter}")
async def generate_chapter_audio(
    slug: str,
    chapter: int,
    voice: str = "af_heart",
    background_tasks: BackgroundTasks = None
):
    """
    Generate audio for a chapter (async background task).
    """
    # Check if already exists
    status = await get_audio_status(slug, chapter)
    if status["exists"]:
        return {
            "status": "exists",
            "url": status["url"],
            "duration": status["duration"]
        }
    
    if status["generating"]:
        return {
            "status": "already_generating",
            "message": "Audio generation in progress"
        }
    
    # Create database record
    audio_record = Audio(
        novel_slug=slug,
        chapter_number=chapter,
        status="generating",
        voice=voice
    )
    db.add(audio_record)
    db.commit()
    
    # Start background task
    background_tasks.add_task(
        _generate_audio_task,
        slug,
        chapter,
        voice,
        audio_record.id
    )
    
    return {
        "status": "queued",
        "message": "Audio generation started"
    }


async def _generate_audio_task(slug: str, chapter: int, voice: str, record_id: int):
    """
    Background task to generate chapter audio.
    """
    try:
        # Use the function from Step 2
        result = await generate_chapter_audio(slug, chapter, voice)
        
        # Update database
        audio_record = db.query(Audio).get(record_id)
        audio_record.status = "completed"
        audio_record.url = result["audio_url"]
        audio_record.duration = result["duration"]
        db.commit()
        
    except Exception as e:
        # Mark as failed
        audio_record = db.query(Audio).get(record_id)
        audio_record.status = "failed"
        audio_record.error = str(e)
        db.commit()

# ==================== Audio Streaming ====================

@router.get("/stream/{slug}/{chapter}")
async def stream_audio(slug: str, chapter: int):
    """
    Get URL for streaming chapter audio.
    """
    audio_record = db.query(Audio).filter_by(
        novel_slug=slug,
        chapter_number=chapter,
        status="completed"
    ).first()
    
    if not audio_record:
        raise HTTPException(404, "Audio not found")
    
    # Return R2 URL (browser fetches directly from R2)
    return RedirectResponse(audio_record.url)

# ==================== Timing Data ====================

@router.get("/timings/{slug}/{chapter}")
async def get_audio_timings(slug: str, chapter: int):
    """
    Get chunk timing data for karaoke highlighting.
    """
    timings = db.query(AudioTiming).filter_by(
        novel_slug=slug,
        chapter_number=chapter
    ).order_by(AudioTiming.start_time).all()
    
    if not timings:
        raise HTTPException(404, "Timings not found")
    
    return {
        "chunks": [
            {
                "start": t.start_time,
                "end": t.end_time,
                "text": t.text
            }
            for t in timings
        ]
    }
```

---

### Step 4: Database Schema

**Add to your models:**

```python
class Audio(Base):
    __tablename__ = "audio"
    
    id = Column(Integer, primary_key=True)
    novel_slug = Column(String, nullable=False)
    chapter_number = Column(Integer, nullable=False)
    voice = Column(String, default="af_heart")
    status = Column(String, default="pending")  # pending, generating, completed, failed
    url = Column(String, nullable=True)  # R2 URL for final audio
    duration = Column(Float, nullable=True)  # Total duration in seconds
    error = Column(String, nullable=True)
    progress = Column(Float, default=0.0)  # 0-100%
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_audio_lookup', 'novel_slug', 'chapter_number'),
    )


class AudioTiming(Base):
    __tablename__ = "audio_timings"
    
    id = Column(Integer, primary_key=True)
    novel_slug = Column(String, nullable=False)
    chapter_number = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)  # Seconds
    end_time = Column(Float, nullable=False)    # Seconds
    text = Column(Text, nullable=False)          # Chunk text
    
    __table_args__ = (
        Index('idx_timing_lookup', 'novel_slug', 'chapter_number'),
    )
```

---

### Step 5: Frontend Integration (Already Done!)

Your existing `AudioPlayer.jsx` and `ChapterReader.jsx` already implement this pattern correctly:

```javascript
// 1. Fetch audio status
const status = await getAudioStatus(slug, chapter);

// 2. Generate if needed
if (!status.exists) {
    await generateAudio(slug, chapter, voice);
}

// 3. Stream audio (single file)
const audioUrl = getAudioStreamUrl(slug, chapter);

// 4. Fetch timings for highlighting
const timings = await fetch(getAudioTimingsUrl(slug, chapter));

// 5. Sync highlighting with audio playback
audio.addEventListener('timeupdate', () => {
    const currentChunk = timings.chunks.find(
        c => audio.currentTime >= c.start && audio.currentTime < c.end
    );
    highlightChunk(currentChunk);
});
```

**No changes needed on frontend!**

---

## 🔄 Alternative Option 2: Client-Side Concatenation (NOT RECOMMENDED)

**How it works:**
1. Generate all chunks separately
2. Store all chunk URLs
3. Frontend downloads all chunks
4. Use Web Audio API to concatenate in browser
5. Play concatenated audio

**Why NOT recommended:**
- ❌ Complex implementation
- ❌ High bandwidth usage (download all upfront)
- ❌ Slow initial load
- ❌ Battery drain on mobile
- ❌ Won't work offline

---

## 📊 COMPARISON TABLE

| Aspect | Separate Chunks | Full Audio + Timings | Client Concatenation |
|--------|----------------|---------------------|---------------------|
| **Playback** | ❌ Choppy | ✅ Smooth | ⚠️ Complex |
| **Bandwidth** | ❌ High | ✅ Efficient | ❌ Very High |
| **Highlighting** | ❌ Hard | ✅ Easy | ⚠️ Moderate |
| **Storage** | ❌ 50+ files | ✅ 1 file | ❌ 50+ files |
| **Implementation** | ⚠️ Moderate | ✅ Simple | ❌ Complex |
| **Mobile** | ❌ Poor | ✅ Great | ❌ Bad |
| **Recommended** | ❌ No | ✅ YES | ❌ No |

---

## 🎬 FINAL WORKFLOW

### User clicks "Listen" button:

```
1. Frontend → Backend: POST /api/audio/generate/novel-slug/1
   ├─> Backend checks if audio exists
   ├─> If not, starts background job:
   │   ├─> Segment text into chunks
   │   ├─> For each chunk:
   │   │   ├─> Call Lightning TTS
   │   │   ├─> Download audio bytes
   │   │   └─> Track timing
   │   ├─> Concatenate all audio
   │   ├─> Upload final.wav to R2
   │   └─> Save timings to DB
   └─> Return: { status: "queued" }

2. Frontend polls: GET /api/audio/status/novel-slug/1
   └─> Backend: { exists: false, generating: true }
   
3. [30-60 seconds later]
   Frontend polls again
   └─> Backend: { exists: true, url: "..." }

4. Frontend: Load audio
   ├─> GET /api/audio/stream/novel-slug/1 → R2 URL
   ├─> GET /api/audio/timings/novel-slug/1 → JSON
   └─> Play audio + sync highlighting

5. As audio plays:
   ├─> audio.currentTime = 5.2 seconds
   ├─> Find chunk: chunks.find(c => 5.2 >= c.start && 5.2 < c.end)
   └─> Highlight that chunk in UI
```

---

## 💾 STORAGE OPTIMIZATION

### Keep or Delete Chunk Files?

**Option A: Keep chunks (more storage)**
- Pro: Can regenerate full audio if needed
- Pro: Can create different versions (fast, slow)
- Con: 50x more files
- Con: Higher R2 costs

**Option B: Delete chunks after concatenation**
- Pro: Minimal storage (1 file per chapter)
- Pro: Lower costs
- Con: Must regenerate all if corruption

**Recommendation:** Delete chunks after successful concatenation. If regeneration is needed, re-run the full process.

---

## 📈 PERFORMANCE ESTIMATES

**For a typical chapter:**
- Text: ~5000 words
- Chunks: ~50 segments
- Audio per chunk: ~2-3 seconds
- Total audio: ~2-3 minutes

**Generation time:**
- TTS per chunk: ~1-2 seconds
- 50 chunks × 2 seconds = **~100 seconds** (parallel possible)
- Concatenation: ~2 seconds
- Upload: ~5 seconds
- **Total: ~2 minutes**

**Storage:**
- Full audio: ~3 MB (3 min × 1 MB/min)
- Per chapter: **~3 MB**
- 100 chapters: **~300 MB**

---

## ✅ RECOMMENDATIONS SUMMARY

1. ✅ **Use Full Audio + Timings approach** (Option 1)
2. ✅ Keep Lightning TTS as-is (minimal changes)
3. ✅ Backend concatenates chunks into single audio file
4. ✅ Store timing data in database
5. ✅ Frontend already implements correct pattern
6. ✅ Delete temporary chunk files after concatenation
7. ✅ Use background tasks for generation (don't block API)

---

## 🚀 NEXT STEPS

1. **Add audio concatenation logic** to backend
2. **Create Audio and AudioTiming database models**
3. **Implement background task queue** (Celery or FastAPI BackgroundTasks)
4. **Add polling logic** to frontend (already exists in AudioPlayer)
5. **Test with real chapter** to verify timing accuracy
6. **Deploy Lightning TTS** to Lightning AI
7. **Configure R2 bucket** with public access
8. **Add progress tracking** (optional but nice UX)

---

## 🐛 DEBUGGING TIPS

1. **Test TTS service independently:**
   ```bash
   curl -X POST http://your-lightning-tts/synthesize \
     -H "Content-Type: application/json" \
     -d '{"text":"Hello world","voice":"af_heart","segment_id":"test_1"}'
   ```

2. **Test concatenation locally:**
   ```python
   from pydub import AudioSegment
   
   audio1 = AudioSegment.from_wav("chunk1.wav")
   audio2 = AudioSegment.from_wav("chunk2.wav")
   combined = audio1 + audio2
   combined.export("full.wav", format="wav")
   ```

3. **Verify timing accuracy:**
   - Play audio and check if highlights match speech
   - Adjust segmentation if chunks are too short/long

---

**This architecture is production-ready, scalable, and matches your current frontend implementation perfectly!**

🏗️ The "Double-Wake" Strategy

To avoid the Lightning studio sleep every 10 min so that we don't get 500 error later . we should use this logic ->

Because Render also sleeps every 15 min of inactivity , we need a two-step process to get everything moving:

    The Initial Wake-up: When a user visits your Vercel site, the first request wakes up Render (takes ~30s).

    The Chain Reaction: As soon as Render starts, it immediately pings Lightning AI to start its wake-up process.

    The Heartbeat: While Render is awake, it "pokes" Lightning every 9 minutes to reset the 10-minute sleep timer.