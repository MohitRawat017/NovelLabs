"""
Audio API routes - handles TTS generation and audio streaming
"""

from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from typing import Optional

from ..database import get_db, dict_from_row

router = APIRouter()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_DIR = BASE_DIR / "audio"


@router.get("/chapter/{chapter_id}")
async def get_chapter_audio(chapter_id: int):
    """Get audio file for a chapter"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT audio_path FROM chapters WHERE id = ?', (chapter_id,))
        chapter = cursor.fetchone()
        
        if not chapter or not chapter['audio_path']:
            raise HTTPException(status_code=404, detail="Audio not found")
        
        audio_path = Path(chapter['audio_path'])
        
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        audio_path, 
        media_type="audio/wav",
        filename=audio_path.name
    )


@router.get("/novel/{slug}/{chapter_number}")
async def get_chapter_audio_by_number(slug: str, chapter_number: int):
    """Get audio file by novel slug and chapter number"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get novel
        cursor.execute('SELECT id FROM novels WHERE slug = ?', (slug,))
        novel = cursor.fetchone()
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        
        # Get chapter
        cursor.execute('''
            SELECT audio_path FROM chapters 
            WHERE novel_id = ? AND chapter_number = ?
        ''', (novel['id'], chapter_number))
        chapter = cursor.fetchone()
        
        if not chapter or not chapter['audio_path']:
            raise HTTPException(status_code=404, detail="Audio not found")
        
        audio_path = Path(chapter['audio_path'])
        
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
    
    return FileResponse(
        audio_path,
        media_type="audio/wav", 
        filename=audio_path.name
    )


@router.post("/generate/{chapter_id}")
async def generate_audio(chapter_id: int, voice: str = "af_heart"):
    """Generate audio for a chapter using TTS (placeholder for now)"""
    # This would trigger the TTS generator
    # For now, return a message
    return {
        "message": "Audio generation queued",
        "chapter_id": chapter_id,
        "voice": voice
    }


@router.get("/voices")
async def list_voices():
    """List available TTS voices"""
    voices = {
        "American English": ["af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky", 
                            "am_adam", "am_michael"],
        "British English": ["bf_emma", "bf_isabella", "bm_george", "bm_lewis"],
        "Japanese": ["jf_alpha", "jf_gongitsune", "jm_kumo"],
        "Mandarin": ["zf_xiaobei", "zf_xiaoni", "zm_yunjian"],
        "Hindi": ["hf_alpha", "hf_beta", "hm_omega"],
        "Spanish": ["ef_dora", "em_alex"],
        "French": ["ff_siwis"],
        "Italian": ["if_sara", "im_nicola"],
        "Portuguese": ["pf_dora", "pm_alex"]
    }
    return voices
