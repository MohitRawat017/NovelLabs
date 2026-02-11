"""
Audio Generation Service for NovelLabs Backend

Handles:
1. Segmenting chapter text into chunks
2. Calling TTS service for each chunk
3. Downloading segment audio from R2
4. Concatenating into full chapter audio
5. Uploading final audio to R2
6. Saving timing data to database
"""

import logging
import asyncio
from typing import List, Dict, Optional
import io

import httpx
from pydub import AudioSegment

from ..config import TTS_SERVICE_URL, TTS_TIMEOUT
from ..r2_client import upload_chapter_audio_to_r2, download_audio_from_url

logger = logging.getLogger(__name__)


class AudioGenerationError(Exception):
    """Raised when audio generation fails."""
    pass


async def generate_chapter_audio(
    novel_slug: str,
    chapter_number: int,
    chapter_text: str,
    voice: str = "af_heart",
    db_session=None
) -> Dict:
    """
    Generate full chapter audio with timing data.
    
    Args:
        novel_slug: Novel identifier
        chapter_number: Chapter number
        chapter_text: Full chapter text content
        voice: TTS voice ID
        db_session: Database session (optional, will create if None)
    
    Returns:
        {
            "audio_url": str,
            "duration": float,
            "chunks": int
        }
    
    Raises:
        AudioGenerationError: If generation fails
    """
    logger.info(f"Starting audio generation for {novel_slug} chapter {chapter_number}")
    
    # 1. Segment chapter text into chunks
    chunks = segment_chapter_text(chapter_text)
    logger.info(f"Segmented into {len(chunks)} chunks")
    
    if not chunks:
        raise AudioGenerationError("No text chunks generated")
    
    # 2. Generate audio for each chunk in parallel (with concurrency limit)
    audio_segments = []
    timings = []
    current_time = 0.0
    
    try:
        # Use semaphore to limit concurrent TTS requests (avoid overwhelming TTS service)
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
        
        async def generate_chunk(idx: int, chunk_text: str):
            async with semaphore:
                return await _generate_single_chunk(
                    novel_slug=novel_slug,
                    chapter_number=chapter_number,
                    chunk_idx=idx,
                    chunk_text=chunk_text,
                    voice=voice
                )
        
        # Generate all chunks concurrently
        tasks = [
            generate_chunk(idx, chunk_text)
            for idx, chunk_text in enumerate(chunks)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for failures
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Chunk {idx} failed: {result}")
                raise AudioGenerationError(f"Failed to generate chunk {idx}: {result}")
        
        # 3. Sort by index and build timing data
        results = sorted(results, key=lambda x: x['index'])
        
        for result in results:
            audio_bytes = result['audio_bytes']
            duration = result['duration']
            chunk_text = result['text']
            
            # Load audio segment
            audio_segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
            audio_segments.append(audio_segment)
            
            # Record timing
            timings.append({
                "start": current_time,
                "end": current_time + duration,
                "text": chunk_text
            })
            
            current_time += duration
        
        logger.info(f"Generated {len(audio_segments)} audio segments, total duration: {current_time:.2f}s")
        
        # 4. Concatenate all audio segments
        logger.info("Concatenating audio segments...")
        final_audio = sum(audio_segments[1:], audio_segments[0])
        
        # 5. Export to bytes
        output_buffer = io.BytesIO()
        final_audio.export(output_buffer, format="wav")
        output_buffer.seek(0)
        final_audio_bytes = output_buffer.read()
        
        logger.info(f"Final audio size: {len(final_audio_bytes) / 1024 / 1024:.2f} MB")
        
        # 6. Upload final audio to R2
        logger.info("Uploading to R2...")
        final_audio_url = upload_chapter_audio_to_r2(
            audio_bytes=final_audio_bytes,
            novel_slug=novel_slug,
            chapter_number=chapter_number
        )
        
        if not final_audio_url:
            raise AudioGenerationError("Failed to upload audio to R2")
        
        logger.info(f"✓ Audio uploaded: {final_audio_url}")
        
        # 7. Save to database
        if db_session:
            _save_audio_to_database(
                db_session=db_session,
                novel_slug=novel_slug,
                chapter_number=chapter_number,
                audio_url=final_audio_url,
                duration=current_time,
                voice=voice,
                timings=timings
            )
            logger.info("✓ Saved to database")
        
        return {
            "audio_url": final_audio_url,
            "duration": current_time,
            "chunks": len(chunks)
        }
        
    except Exception as e:
        logger.error(f"Audio generation failed: {e}", exc_info=True)
        raise AudioGenerationError(f"Generation failed: {e}")


async def _generate_single_chunk(
    novel_slug: str,
    chapter_number: int,
    chunk_idx: int,
    chunk_text: str,
    voice: str
) -> Dict:
    """
    Generate audio for a single chunk.
    
    Returns:
        {
            "index": int,
            "audio_bytes": bytes,
            "duration": float,
            "text": str
        }
    """
    segment_id = f"{novel_slug}_ch{chapter_number:04d}_seg{chunk_idx:04d}"
    
    logger.info(f"Generating chunk {chunk_idx}: {segment_id}")
    
    async with httpx.AsyncClient(timeout=TTS_TIMEOUT) as client:
        # Call TTS service
        response = await client.post(
            f"{TTS_SERVICE_URL}/synthesize",
            json={
                "text": chunk_text,
                "voice": voice,
                "segment_id": segment_id
            }
        )
        
        if response.status_code != 200:
            raise AudioGenerationError(
                f"TTS service returned {response.status_code}: {response.text}"
            )
        
        data = response.json()
        audio_url = data["audio_url"]
        duration = data["duration"]
        
        # Download audio bytes
        logger.info(f"Downloading audio from {audio_url}")
        audio_bytes = download_audio_from_url(audio_url)
        
        if not audio_bytes:
            raise AudioGenerationError(f"Failed to download audio from {audio_url}")
        
        return {
            "index": chunk_idx,
            "audio_bytes": audio_bytes,
            "duration": duration,
            "text": chunk_text
        }


def _save_audio_to_database(
    db_session,
    novel_slug: str,
    chapter_number: int,
    audio_url: str,
    duration: float,
    voice: str,
    timings: List[Dict]
):
    """Save audio record and timing data to database."""
    from ..models.audio import ChapterAudio, AudioTiming
    
    # Create or update Audio record
    audio_record = db_session.query(ChapterAudio).filter_by(
        novel_slug=novel_slug,
        chapter_number=chapter_number
    ).first()
    
    if audio_record:
        # Update existing
        audio_record.url = audio_url
        audio_record.duration = duration
        audio_record.voice = voice
        audio_record.status = "completed"
        audio_record.error = None
    else:
        # Create new
        audio_record = ChapterAudio(
            novel_slug=novel_slug,
            chapter_number=chapter_number,
            url=audio_url,
            duration=duration,
            voice=voice,
            status="completed"
        )
        db_session.add(audio_record)
    
    # Delete old timings
    db_session.query(AudioTiming).filter_by(
        novel_slug=novel_slug,
        chapter_number=chapter_number
    ).delete()
    
    # Insert new timings
    for timing in timings:
        timing_record = AudioTiming(
            novel_slug=novel_slug,
            chapter_number=chapter_number,
            start_time=timing["start"],
            end_time=timing["end"],
            text=timing["text"]
        )
        db_session.add(timing_record)
    
    db_session.commit()


def segment_chapter_text(text: str, target_chars: int = 300) -> List[str]:
    """
    Segment chapter text into chunks for TTS.
    
    Args:
        text: Full chapter text
        target_chars: Target chunk size in characters
    
    Returns:
        List of text chunks
    """
    paragraphs = text.split('\n\n')
    chunks = []
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(para) <= target_chars * 1.5:
            chunks.append(para)
        else:
            # Split long paragraphs by sentences
            sentences = para.replace('! ', '!|').replace('? ', '?|').replace('. ', '.|').split('|')
            current_chunk = ""
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                
                if not current_chunk:
                    current_chunk = sentence
                elif len(current_chunk) + len(sentence) <= target_chars * 1.5:
                    current_chunk += " " + sentence
                else:
                    chunks.append(current_chunk)
                    current_chunk = sentence
            
            if current_chunk:
                chunks.append(current_chunk)
    
    return chunks
