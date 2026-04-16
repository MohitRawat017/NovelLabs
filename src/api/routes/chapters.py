"""Chapters API routes."""

import os
import re
import logging
import httpx
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from ..database import get_db, dict_from_row, list_from_rows
from ..config import NOVEL_OUTPUT_DIR, READ_ONLY_MODE
from ..models.schemas import ChapterResponse, ChapterListResponse, ChapterContentResponse
from ..storage import build_audio_public_url, get_chapter_text

router = APIRouter()
logger = logging.getLogger(__name__)

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_DIR = BASE_DIR / "audio"
_ALLOWED_DATA_ROOT = Path(NOVEL_OUTPUT_DIR).resolve()


def _validate_content_path(content_path: str) -> str:
    """Ensure content_path resolves to within the allowed novel data directory."""
    resolved = Path(content_path).resolve()
    if not str(resolved).startswith(str(_ALLOWED_DATA_ROOT)):
        raise HTTPException(
            status_code=400,
            detail="content_path must be within the novel data directory",
        )
    return str(resolved)


_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "[::1]"}


def _validate_content_url(url: str) -> str:
    """Block internal/metadata URLs to prevent SSRF."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
    hostname = (parsed.hostname or "").lower()
    if hostname in _BLOCKED_HOSTS or hostname.startswith("10.") or hostname.startswith("192.168."):
        raise HTTPException(status_code=400, detail="Internal or metadata URLs are not allowed")
    return url


def _resolve_audio_url(audio_key: Optional[str], audio_url: Optional[str]) -> Optional[str]:
    return build_audio_public_url(audio_key) or audio_url


def _normalize_chapter_audio_metadata(chapter: dict) -> dict:
    audio_path = chapter.get("audio_path")
    audio_key = chapter.get("audio_key")
    audio_status = chapter.get("audio_status")
    has_audio = bool(audio_path or audio_key or chapter.get("has_audio")) or audio_status == "completed"
    chapter["has_audio"] = has_audio
    chapter["audio_status"] = audio_status or ("completed" if has_audio else None)
    if has_audio:
        chapter["audio_provider"] = chapter.get("audio_provider") or "kokoro"
    chapter["audio_url"] = build_audio_public_url(audio_key)
    return chapter


def _read_local_content(content_path: Optional[str]) -> str:
    if not content_path or not os.path.exists(content_path):
        return ""

    with open(content_path, 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')
        if len(lines) > 2:
            return '\n'.join(lines[2:]).strip()
        return content


async def _resolve_chapter_content(chapter: dict) -> str:
    # Production-first read order: key-based object store -> URL -> local path -> DB fallback.
    r2_key = chapter.get("r2_key")
    if r2_key:
        text = get_chapter_text(r2_key)
        if text:
            return text

    content_url = chapter.get("content_url")
    if content_url:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(content_url, timeout=10)
                if resp.status_code == 200:
                    return resp.text
        except Exception as exc:
            logger.warning("Failed to fetch chapter content URL '%s': %s", content_url, exc)

    local_content = _read_local_content(chapter.get("content_path"))
    if local_content:
        return local_content

    return chapter.get("content") or ""


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
            # FIXED: Don't read full content, just first line for title
            try:
                with open(chapter_file, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    title = first_line if first_line else f"Chapter {chapter_number}"
                    
                    # Count words efficiently
                    f.seek(0)
                    content = f.read()
                    word_count = len(content.split())
            except Exception:
                title = f"Chapter {chapter_number}"
                word_count = 0
            
            # Check for audio file
            # Get novel folder name for audio path
            novel_folder = data_dir.name
            audio_file = AUDIO_DIR / novel_folder / f"Chapter_{chapter_number:04d}.wav"
            audio_path = str(audio_file) if audio_file.exists() else None
            
            # Insert or update chapter WITHOUT content
            # Uses PostgreSQL ON CONFLICT for upsert
            cursor.execute('''
                INSERT INTO chapters 
                (novel_id, chapter_number, title, content_path, audio_path, word_count)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (novel_id, chapter_number) 
                DO UPDATE SET
                    title = EXCLUDED.title,
                    content_path = EXCLUDED.content_path,
                    audio_path = EXCLUDED.audio_path,
                    word_count = EXCLUDED.word_count
            ''', (novel_id, chapter_number, title, str(chapter_file), audio_path, word_count))
    
    return len(chapter_files)


from pydantic import BaseModel

class ChapterCreate(BaseModel):
    """Schema for creating a chapter - FIXED VERSION"""
    novel_slug: str
    chapter_number: int
    title: str = "Untitled Chapter"
    content: Optional[str] = None  # FIXED: Made optional (discouraged)
    content_path: Optional[str] = None  # FIXED: Preferred way to store chapters
    word_count: int = 0


class ChapterMetadataCreate(BaseModel):
    """
    Schema for creating chapter metadata ONLY (recommended)
    This prevents database bloat by not storing content
    """
    novel_slug: str
    chapter_number: int
    title: str = "Untitled Chapter"
    content_path: str  # Required - where to find content on filesystem
    word_count: int = 0


class ContentUrlUpdate(BaseModel):
    """Legacy schema for storing a remote chapter content URL."""
    content_url: str


class ContentStorageUpdate(BaseModel):
    """Canonical storage metadata update payload for chapter content/audio keys."""
    r2_key: Optional[str] = None
    content_url: Optional[str] = None
    audio_key: Optional[str] = None
    audio_url: Optional[str] = None
    has_audio: Optional[bool] = None
    status: Optional[str] = None
    audio_provider: Optional[str] = None
    audio_voice: Optional[str] = None
    audio_duration: Optional[float] = None
    audio_progress: Optional[float] = None
    audio_error: Optional[str] = None


@router.patch("/novel/{slug}/{chapter_number}/content-url")
async def update_chapter_content_url(slug: str, chapter_number: int, data: ContentUrlUpdate):
    """
    Legacy endpoint for storing a remote chapter content URL.

    Local-first runs read chapter text from the filesystem. This endpoint is
    kept for backward compatibility only.
    """
    safe_url = _validate_content_url(data.content_url)
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get novel
        cursor.execute('SELECT id FROM novels WHERE slug = ?', (slug,))
        novel = cursor.fetchone()
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        
        # Update chapter
        cursor.execute('''
            UPDATE chapters 
            SET content_url = ?
            WHERE novel_id = ? AND chapter_number = ?
        ''', (safe_url, novel['id'], chapter_number))
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Chapter not found")
        
        conn.commit()
    
    return {"message": "Content URL updated", "content_url": safe_url}


@router.patch("/novel/{slug}/{chapter_number}/storage")
async def update_chapter_storage(slug: str, chapter_number: int, data: ContentStorageUpdate):
    """
    Update canonical chapter storage metadata.

    Intended for local ingestion/upload pipeline use, not public client writes.
    """
    chapter_updates = {}

    if data.r2_key is not None:
        chapter_updates["r2_key"] = data.r2_key.lstrip("/")
    if data.content_url is not None:
        chapter_updates["content_url"] = _validate_content_url(data.content_url)
    if data.audio_key is not None:
        chapter_updates["audio_key"] = data.audio_key.lstrip("/")
    if data.has_audio is not None:
        chapter_updates["has_audio"] = bool(data.has_audio)
    if data.status is not None:
        chapter_updates["status"] = data.status

    audio_metadata_requested = any(
        value is not None
        for value in (
            data.audio_key,
            data.audio_url,
            data.has_audio,
            data.status,
            data.audio_provider,
            data.audio_voice,
            data.audio_duration,
            data.audio_progress,
            data.audio_error,
        )
    )

    if not chapter_updates and not audio_metadata_requested:
        raise HTTPException(status_code=400, detail="No storage fields provided to update")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM novels WHERE slug = ?', (slug,))
        novel = cursor.fetchone()

        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")

        cursor.execute(
            """
            SELECT id, audio_key
            FROM chapters
            WHERE novel_id = ? AND chapter_number = ?
            """,
            (novel['id'], chapter_number),
        )
        chapter_row = dict_from_row(cursor.fetchone())
        if not chapter_row:
            raise HTTPException(status_code=404, detail="Chapter not found")

        if chapter_updates:
            set_parts = []
            params = []
            for field, value in chapter_updates.items():
                set_parts.append(f"{field} = ?")
                params.append(value)

            params.extend([novel['id'], chapter_number])

            cursor.execute(
                f"""
                UPDATE chapters
                SET {', '.join(set_parts)}
                WHERE novel_id = ? AND chapter_number = ?
                """,
                tuple(params),
            )

        if audio_metadata_requested:
            cursor.execute(
                """
                SELECT provider, voice, status, audio_url, duration, error, progress
                FROM chapter_audio
                WHERE novel_slug = ? AND chapter_number = ?
                """,
                (slug, chapter_number),
            )
            existing_audio = dict_from_row(cursor.fetchone()) or {}

            effective_audio_key = chapter_updates.get("audio_key", chapter_row.get("audio_key"))
            effective_audio_url = (
                _validate_content_url(data.audio_url)
                if data.audio_url is not None
                else _resolve_audio_url(effective_audio_key, existing_audio.get("audio_url"))
            )
            audio_status = (
                data.status
                or existing_audio.get("status")
                or ("completed" if (data.has_audio is True or effective_audio_url or effective_audio_key) else "pending")
            )
            audio_provider = data.audio_provider or existing_audio.get("provider") or "kokoro"
            audio_voice = data.audio_voice or existing_audio.get("voice") or "af_heart"
            audio_duration = data.audio_duration if data.audio_duration is not None else existing_audio.get("duration")
            audio_error = data.audio_error if data.audio_error is not None else existing_audio.get("error")
            audio_progress = (
                data.audio_progress
                if data.audio_progress is not None
                else (100.0 if audio_status == "completed" or data.has_audio is True else existing_audio.get("progress") or 0.0)
            )

            cursor.execute(
                """
                INSERT INTO chapter_audio
                    (novel_slug, chapter_number, provider, voice, status, audio_url, duration, error, progress, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (novel_slug, chapter_number)
                DO UPDATE SET
                    provider = excluded.provider,
                    voice = excluded.voice,
                    status = excluded.status,
                    audio_url = excluded.audio_url,
                    duration = excluded.duration,
                    error = excluded.error,
                    progress = excluded.progress,
                    updated_at = excluded.updated_at
                """,
                (
                    slug,
                    chapter_number,
                    audio_provider,
                    audio_voice,
                    audio_status,
                    effective_audio_url,
                    audio_duration,
                    audio_error,
                    audio_progress,
                    datetime.utcnow(),
                    datetime.utcnow(),
                ),
            )

    updated_fields = set(chapter_updates.keys())
    if audio_metadata_requested:
        updated_fields.update(
            {
                "audio_url",
                "audio_provider",
                "audio_voice",
                "audio_duration",
                "audio_progress",
                "audio_error",
            }
        )
    return {"message": "Chapter storage metadata updated", "updated_fields": sorted(updated_fields)}


@router.post("/metadata")
async def create_chapter_metadata(chapter: ChapterMetadataCreate):
    """
    Create chapter with metadata only (RECOMMENDED)
    
    FIXED: This endpoint only stores metadata, not content.
    Content is read from content_path when needed.
    
    Benefits:
    - smaller SQLite database
    - faster local API responses
    - chapter text stays in plain files under data/output
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get novel ID from slug
        cursor.execute('SELECT id FROM novels WHERE slug = ?', (chapter.novel_slug,))
        novel = cursor.fetchone()
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        
        novel_id = novel['id'] if hasattr(novel, '__getitem__') else novel[0]
        
        # Check if chapter already exists
        cursor.execute(
            'SELECT id FROM chapters WHERE novel_id = ? AND chapter_number = ?',
            (novel_id, chapter.chapter_number)
        )
        existing = cursor.fetchone()
        
        if existing:
            raise HTTPException(status_code=409, detail="Chapter already exists")
        
        # FIXED: Insert chapter WITHOUT content column
        safe_path = _validate_content_path(chapter.content_path)
        cursor.execute('''
            INSERT INTO chapters (novel_id, chapter_number, title, content_path, word_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (novel_id, chapter.chapter_number, chapter.title, 
              safe_path, chapter.word_count))
        
        conn.commit()
        
        # Update novel's chapter count
        cursor.execute('''
            UPDATE novels SET chapter_count = (
                SELECT COUNT(*) FROM chapters WHERE novel_id = ?
            ) WHERE id = ?
        ''', (novel_id, novel_id))
        
        conn.commit()
        
        return {
            "message": "Chapter metadata created", 
            "chapter_number": chapter.chapter_number,
            "storage_saved": "~10 KB (content not stored in DB)"
        }


@router.post("")
async def create_chapter(chapter: ChapterCreate):
    """
    Create a chapter (LEGACY - for backward compatibility)
    
    WARNING: If you provide 'content', it will be stored in the database.
    This causes bloat. Use POST /metadata endpoint instead.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get novel ID from slug
        cursor.execute('SELECT id FROM novels WHERE slug = ?', (chapter.novel_slug,))
        novel = cursor.fetchone()
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        
        novel_id = novel['id'] if hasattr(novel, '__getitem__') else novel[0]
        
        # Check if chapter already exists
        cursor.execute(
            'SELECT id FROM chapters WHERE novel_id = ? AND chapter_number = ?',
            (novel_id, chapter.chapter_number)
        )
        existing = cursor.fetchone()
        
        if existing:
            raise HTTPException(status_code=409, detail="Chapter already exists")
        
        # Calculate word count if not provided
        word_count = chapter.word_count
        if not word_count and chapter.content:
            word_count = len(chapter.content.split())
        
        # FIXED: Prefer content_path over content
        if chapter.content_path:
            # Store only metadata
            safe_path = _validate_content_path(chapter.content_path)
            cursor.execute('''
                INSERT INTO chapters (novel_id, chapter_number, title, content_path, word_count)
                VALUES (?, ?, ?, ?, ?)
            ''', (novel_id, chapter.chapter_number, chapter.title, 
                  safe_path, word_count))
        elif chapter.content:
            # LEGACY: Store content (causes bloat)
            print(f"[WARN] Storing content in DB for chapter {chapter.chapter_number} - consider using content_path instead")
            cursor.execute('''
                INSERT INTO chapters (novel_id, chapter_number, title, content, word_count)
                VALUES (?, ?, ?, ?, ?)
            ''', (novel_id, chapter.chapter_number, chapter.title, chapter.content, word_count))
        else:
            raise HTTPException(status_code=400, detail="Must provide either content or content_path")
        
        conn.commit()
        
        # Update novel's chapter count
        cursor.execute('''
            UPDATE novels SET chapter_count = (
                SELECT COUNT(*) FROM chapters WHERE novel_id = ?
            ) WHERE id = ?
        ''', (novel_id, novel_id))
        
        conn.commit()
        
        return {"message": "Chapter created", "chapter_number": chapter.chapter_number}


@router.get("/novel/{slug}", response_model=ChapterListResponse)
async def list_chapters(
    slug: str,
    sort: str = Query("asc", pattern="^(asc|desc)$"),
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
        
        # Sync chapters from filesystem only for mutable local deployments.
        if data_path and not READ_ONLY_MODE:
            sync_chapters_for_novel(novel_id, data_path)
        
        # Get chapters with audio metadata
        order = "ASC" if sort == "asc" else "DESC"
        query = f"""
            SELECT
                c.*,
                COALESCE(ca.provider, CASE WHEN c.audio_path IS NOT NULL THEN 'kokoro' END) AS audio_provider,
                COALESCE(ca.status, CASE WHEN c.audio_path IS NOT NULL THEN 'completed' END) AS audio_status
            FROM chapters c
            LEFT JOIN chapter_audio ca
                ON ca.novel_slug = ? AND ca.chapter_number = c.chapter_number
            WHERE c.novel_id = ?
        """
        params = [slug, novel_id]

        if search:
            query += ' AND (c.title LIKE ? OR c.chapter_number = ?)'
            params.extend([f'%{search}%', search if search.isdigit() else -1])

        query += f' ORDER BY c.chapter_number {order}'

        cursor.execute(query, params)
        chapters = [_normalize_chapter_audio_metadata(chapter) for chapter in list_from_rows(cursor.fetchall())]
        
    return ChapterListResponse(chapters=chapters, total=len(chapters))


@router.get("/{chapter_id}", response_model=ChapterContentResponse)
async def get_chapter(chapter_id: int):
    """Get chapter content by ID"""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            '''
            SELECT c.*, n.slug AS novel_slug
            FROM chapters c
            JOIN novels n ON n.id = c.novel_id
            WHERE c.id = ?
            ''',
            (chapter_id,),
        )
        chapter = dict_from_row(cursor.fetchone())

        if not chapter:
            raise HTTPException(status_code=404, detail="Chapter not found")

        content = await _resolve_chapter_content(chapter)

        cursor.execute(
            '''
            SELECT status, audio_url
            FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
            ''',
            (chapter['novel_slug'], chapter['chapter_number']),
        )
        audio_meta = dict_from_row(cursor.fetchone())

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

    audio_url = _resolve_audio_url(chapter.get('audio_key'), audio_meta.get('audio_url') if audio_meta else None)

    has_audio = bool(
        chapter.get('audio_key')
        or chapter.get('audio_path')
        or chapter.get('has_audio')
        or (audio_meta and audio_meta.get('status') == 'completed')
    )
    
    return ChapterContentResponse(
        id=chapter['id'],
        novel_id=chapter['novel_id'],
        chapter_number=chapter['chapter_number'],
        title=chapter['title'] or f"Chapter {chapter['chapter_number']}",
        content=content,
        has_audio=has_audio,
        audio_url=audio_url,
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

        content = await _resolve_chapter_content(chapter)

        cursor.execute(
            '''
            SELECT status, audio_url
            FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
            ''',
            (slug, chapter_number),
        )
        audio_meta = dict_from_row(cursor.fetchone())
        
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

    audio_url = _resolve_audio_url(chapter.get('audio_key'), audio_meta.get('audio_url') if audio_meta else None)

    has_audio = bool(
        chapter.get('audio_key')
        or chapter.get('audio_path')
        or chapter.get('has_audio')
        or (audio_meta and audio_meta.get('status') == 'completed')
    )
    
    return ChapterContentResponse(
        id=chapter['id'],
        novel_id=chapter['novel_id'],
        chapter_number=chapter['chapter_number'],
        title=chapter['title'] or f"Chapter {chapter_number}",
        content=content,
        has_audio=has_audio,
        audio_url=audio_url,
        prev_chapter=prev_chapter,
        next_chapter=next_chapter
    )


@router.post("/admin/cleanup-content")
async def cleanup_chapter_content():
    """
    Remove chapter content from database to save storage space
    
    This is safe because content is read from filesystem (content_path).
    Expected savings: ~90% of database size
    """
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get stats before
        cursor.execute('SELECT COUNT(*) FROM chapters WHERE content IS NOT NULL')
        before_result = cursor.fetchone()
        before_count = before_result[0] if isinstance(before_result, (list, tuple)) else before_result.get('count', 0)
        
        # Clear content column
        cursor.execute('UPDATE chapters SET content = NULL WHERE content IS NOT NULL')
        affected = cursor.rowcount
        
        conn.commit()
        
        # Estimate savings (average 10KB per chapter)
        savings_mb = (affected * 10) / 1024
        
        return {
            'message': 'Content cleanup complete',
            'chapters_cleaned': affected,
            'before': before_count,
            'estimated_savings_mb': round(savings_mb, 2)
        }
