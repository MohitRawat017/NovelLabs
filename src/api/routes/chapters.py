"""
Chapters API routes
"""

import os
import re
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from ..database import get_db, dict_from_row, list_from_rows
from ..models.schemas import ChapterResponse, ChapterListResponse, ChapterContentResponse

router = APIRouter()

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_DIR = BASE_DIR / "audio"


def sync_chapters_for_novel(novel_id: int, data_path: str):
    """Sync chapters from filesystem to database for a novel"""
    data_dir = Path(data_path)
    
    if not data_dir.exists():
        return 0
    
    chapter_files = sorted(data_dir.glob("Chapter_*.txt"))
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        for chapter_file in chapter_files:
            # Extract chapter number from filename (Chapter_0001.txt)
            match = re.search(r'Chapter_(\d+)', chapter_file.name)
            if not match:
                continue
            
            chapter_number = int(match.group(1))
            
            # Read chapter to get title and word count
            try:
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    title = lines[0].strip() if lines else f"Chapter {chapter_number}"
                    word_count = len(content.split())
            except Exception:
                title = f"Chapter {chapter_number}"
                word_count = 0
            
            # Check for audio file
            # Get novel folder name for audio path
            novel_folder = data_dir.name
            audio_file = AUDIO_DIR / novel_folder / f"Chapter_{chapter_number:04d}.wav"
            audio_path = str(audio_file) if audio_file.exists() else None
            
            # Insert or update chapter
            cursor.execute('''
                INSERT OR REPLACE INTO chapters 
                (novel_id, chapter_number, title, content_path, audio_path, word_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (novel_id, chapter_number, title, str(chapter_file), audio_path, word_count))
    
    return len(chapter_files)


@router.get("/novel/{slug}", response_model=ChapterListResponse)
async def list_chapters(
    slug: str,
    sort: str = Query("asc", regex="^(asc|desc)$"),
    search: Optional[str] = Query(None)
):
    """Get all chapters for a novel"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get novel
        cursor.execute('SELECT id, data_path FROM novels WHERE slug = ?', (slug,))
        novel = cursor.fetchone()
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        
        novel_id, data_path = novel['id'], novel['data_path']
        
        # Sync chapters from filesystem
        if data_path:
            sync_chapters_for_novel(novel_id, data_path)
        
        # Get chapters
        order = "ASC" if sort == "asc" else "DESC"
        query = f'SELECT * FROM chapters WHERE novel_id = ?'
        params = [novel_id]
        
        if search:
            query += ' AND (title LIKE ? OR chapter_number = ?)'
            params.extend([f'%{search}%', search if search.isdigit() else -1])
        
        query += f' ORDER BY chapter_number {order}'
        
        cursor.execute(query, params)
        chapters = list_from_rows(cursor.fetchall())
        
    return ChapterListResponse(chapters=chapters, total=len(chapters))


@router.get("/{chapter_id}", response_model=ChapterContentResponse)
async def get_chapter(chapter_id: int):
    """Get chapter content by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,))
        chapter = dict_from_row(cursor.fetchone())
        
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        
        # Read content from file
        content = ""
        if chapter['content_path'] and os.path.exists(chapter['content_path']):
            with open(chapter['content_path'], 'r', encoding='utf-8') as f:
                content = f.read()
                # Skip the title and separator lines
                lines = content.split('\n')
                if len(lines) > 2:
                    content = '\n'.join(lines[2:]).strip()
        
        # Get prev/next chapter numbers
        cursor.execute('''
            SELECT chapter_number FROM chapters 
            WHERE novel_id = ? AND chapter_number < ?
            ORDER BY chapter_number DESC LIMIT 1
        ''', (chapter['novel_id'], chapter['chapter_number']))
        prev_row = cursor.fetchone()
        prev_chapter = prev_row['chapter_number'] if prev_row else None
        
        cursor.execute('''
            SELECT chapter_number FROM chapters 
            WHERE novel_id = ? AND chapter_number > ?
            ORDER BY chapter_number ASC LIMIT 1
        ''', (chapter['novel_id'], chapter['chapter_number']))
        next_row = cursor.fetchone()
        next_chapter = next_row['chapter_number'] if next_row else None
    
    return ChapterContentResponse(
        id=chapter['id'],
        novel_id=chapter['novel_id'],
        chapter_number=chapter['chapter_number'],
        title=chapter['title'] or f"Chapter {chapter['chapter_number']}",
        content=content,
        has_audio=bool(chapter['audio_path']),
        prev_chapter=prev_chapter,
        next_chapter=next_chapter
    )


@router.get("/novel/{slug}/{chapter_number}", response_model=ChapterContentResponse)
async def get_chapter_by_number(slug: str, chapter_number: int):
    """Get chapter content by novel slug and chapter number"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get novel
        cursor.execute('SELECT id, data_path FROM novels WHERE slug = ?', (slug,))
        novel = cursor.fetchone()
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        
        novel_id = novel['id']
        
        # Get chapter
        cursor.execute('''
            SELECT * FROM chapters 
            WHERE novel_id = ? AND chapter_number = ?
        ''', (novel_id, chapter_number))
        chapter = dict_from_row(cursor.fetchone())
        
        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")
        
        # Read content from file
        content = ""
        if chapter['content_path'] and os.path.exists(chapter['content_path']):
            with open(chapter['content_path'], 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                if len(lines) > 2:
                    content = '\n'.join(lines[2:]).strip()
        
        # Get prev/next
        cursor.execute('''
            SELECT chapter_number FROM chapters 
            WHERE novel_id = ? AND chapter_number < ?
            ORDER BY chapter_number DESC LIMIT 1
        ''', (novel_id, chapter_number))
        prev_row = cursor.fetchone()
        prev_chapter = prev_row['chapter_number'] if prev_row else None
        
        cursor.execute('''
            SELECT chapter_number FROM chapters 
            WHERE novel_id = ? AND chapter_number > ?
            ORDER BY chapter_number ASC LIMIT 1
        ''', (novel_id, chapter_number))
        next_row = cursor.fetchone()
        next_chapter = next_row['chapter_number'] if next_row else None
    
    return ChapterContentResponse(
        id=chapter['id'],
        novel_id=chapter['novel_id'],
        chapter_number=chapter['chapter_number'],
        title=chapter['title'] or f"Chapter {chapter_number}",
        content=content,
        has_audio=bool(chapter['audio_path']),
        prev_chapter=prev_chapter,
        next_chapter=next_chapter
    )
