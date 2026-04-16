"""Novels API routes."""

import asyncio
import os
import re
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form, Body
from typing import Optional, List

from ..database import get_db, dict_from_row, list_from_rows, db_execute
from ..config import (
    AUTO_SYNC_NOVELS_ON_STARTUP,
    DATABASE_BACKEND,
    NOVEL_OUTPUT_DIR,
    SQLITE_DB_PATH,
)
from ..models.schemas import NovelResponse, NovelListResponse, NovelCreate, NovelUpdateRequest

router = APIRouter()
logger = logging.getLogger(__name__)

# Base directory for scraped data
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = NOVEL_OUTPUT_DIR

STORAGE_TABLES = [
    "novels",
    "chapters",
    "audio_segments",
    "chapter_audio",
    "audio_timings",
    "novel_tts_profiles",
    "user_progress",
    "user_preferences",
]

RESET_DELETE_ORDER = [
    "audio_timings",
    "audio_segments",
    "chapter_audio",
    "novel_tts_profiles",
    "user_progress",
    "chapters",
    "novels",
    "user_preferences",
]

RESET_SEQUENCE_TABLES = [
    "novels",
    "chapters",
    "audio_segments",
    "chapter_audio",
    "audio_timings",
    "novel_tts_profiles",
    "user_progress",
    "user_preferences",
]


def slugify(value: str) -> str:
    slug = value.lower().replace(" ", "-")
    return re.sub(r"[^a-z0-9-]", "", slug)


def sanitize_folder_name(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "", value).strip()
    return cleaned or "Imported Novel"


def title_from_folder_name(folder_name: str) -> str:
    title = re.sub(r"[_-]+", " ", folder_name).strip()
    return title or "Imported Novel"


def parse_uploaded_chapter_number(filename: str) -> Optional[int]:
    stem = Path(filename).stem.lower()
    for pattern in (r"chapter[\s_-]*(\d+)", r"^(\d+)", r"(\d+)"):
        match = re.search(pattern, stem)
        if match:
            return int(match.group(1))
    return None


def chapter_title_from_filename(filename: str, chapter_number: int) -> str:
    stem = Path(filename).stem
    cleaned = re.sub(r"(?i)^chapter[\s_-]*\d+[\s_-]*", "", stem).strip(" -_")
    if cleaned:
        cleaned = re.sub(r"[_-]+", " ", cleaned).strip()
        return f"Chapter {chapter_number}: {cleaned.title()}"
    return f"Chapter {chapter_number}"


def normalize_uploaded_chapter_content(raw_text: str, default_title: str) -> tuple[str, str]:
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return default_title, default_title

    lines = normalized.split("\n")
    if len(lines) >= 3 and re.fullmatch(r"=+", lines[1].strip()):
        title = lines[0].strip() or default_title
        body = "\n".join(lines[2:]).strip()
        return title, body or title

    return default_title, normalized


def scan_novels_from_filesystem():
    """Scan the data/output directory for scraped novels"""
    novels = []
    
    if not DATA_DIR.exists():
        return novels
    
    for folder in DATA_DIR.iterdir():
        if folder.is_dir() and not folder.name.startswith('.'):
            # Count chapters
            chapter_files = list(folder.glob("Chapter_*.txt"))
            chapter_count = len(chapter_files)
            
            if chapter_count > 0:
                # Create slug from folder name
                slug = slugify(folder.name)
                
                # Get last modified time
                latest_file = max(chapter_files, key=lambda f: f.stat().st_mtime)
                last_updated = datetime.fromtimestamp(latest_file.stat().st_mtime)
                
                novels.append({
                    'slug': slug,
                    'title': folder.name.replace('-', ' ').title(),
                    'description': f'Novel with {chapter_count} chapters',
                    'genres': 'Fantasy,Action',  # Default genres
                    'chapter_count': chapter_count,
                    'data_path': str(folder),
                    'source_toc_url': None,
                    'last_updated': last_updated
                })
    
    return novels


def _read_count(cursor, table: str) -> int:
    cursor.execute(f"SELECT COUNT(*) AS count FROM {table}")
    row = cursor.fetchone()
    return int(row["count"] if hasattr(row, "keys") else row[0])


def _collect_storage_counts(cursor) -> dict:
    return {table: _read_count(cursor, table) for table in STORAGE_TABLES}


def _vacuum_sqlite_db() -> None:
    db_path = Path(SQLITE_DB_PATH)
    with sqlite3.connect(db_path, timeout=30) as raw_conn:
        raw_conn.execute("VACUUM")


@router.get("/admin/storage-stats")
async def storage_stats():
    """Return per-table storage counts for DB reset/debug workflows."""
    with get_db() as conn:
        cursor = conn.cursor()
        counts = _collect_storage_counts(cursor)

    return {
        "database_backend": DATABASE_BACKEND,
        "auto_sync_novels_on_startup": AUTO_SYNC_NOVELS_ON_STARTUP,
        "filesystem_novel_count": len(scan_novels_from_filesystem()),
        "counts": counts,
    }


@router.post("/admin/reset-database")
async def reset_database(
    confirm: str = Body(..., embed=True),
    reseed_preferences: bool = Body(True, embed=True),
    reset_sequences: bool = Body(True, embed=True),
    vacuum: bool = Body(False, embed=True),
):
    """
    DANGER: Wipe all SQLite data tables while keeping source filesystem data intact.

    Requires {"confirm": "DELETE ALL"} in the JSON body.
    """
    if confirm != "DELETE ALL":
        raise HTTPException(
            status_code=400,
            detail='Send {"confirm": "DELETE ALL"} in the request body to confirm this destructive action.',
        )
    if DATABASE_BACKEND != "sqlite":
        raise HTTPException(
            status_code=403,
            detail="Full database wipe is only enabled for SQLite mode.",
        )

    with get_db() as conn:
        cursor = conn.cursor()
        counts_before = _collect_storage_counts(cursor)

        for table in RESET_DELETE_ORDER:
            cursor.execute(f"DELETE FROM {table}")

        if reset_sequences:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            )
            if cursor.fetchone():
                placeholders = ", ".join(["?"] * len(RESET_SEQUENCE_TABLES))
                cursor.execute(
                    f"DELETE FROM sqlite_sequence WHERE name IN ({placeholders})",
                    tuple(RESET_SEQUENCE_TABLES),
                )

        if reseed_preferences:
            cursor.execute("INSERT INTO user_preferences DEFAULT VALUES")

        counts_after = _collect_storage_counts(cursor)

    vacuumed = False
    vacuum_error = None
    if vacuum:
        try:
            _vacuum_sqlite_db()
            vacuumed = True
        except Exception as exc:
            vacuum_error = str(exc)
            logger.warning("SQLite VACUUM failed after reset: %s", exc)

    logger.warning(
        "Full SQLite reset completed (reseed_preferences=%s, reset_sequences=%s, vacuum=%s)",
        reseed_preferences,
        reset_sequences,
        vacuumed,
    )

    return {
        "message": "SQLite database reset completed",
        "counts_before": counts_before,
        "counts_after": counts_after,
        "reseed_preferences": reseed_preferences,
        "reset_sequences": reset_sequences,
        "vacuum_requested": vacuum,
        "vacuumed": vacuumed,
        "vacuum_error": vacuum_error,
    }


def sync_novels_to_db():
    """Sync filesystem novels to database"""
    novels = scan_novels_from_filesystem()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        for novel in novels:
            # Check if novel exists
            cursor.execute('SELECT id, chapter_count, source_toc_url FROM novels WHERE slug = ?', (novel['slug'],))
            existing = cursor.fetchone()
            
            if existing:
                existing_count = int(existing['chapter_count'] or 0)
                local_count = int(novel['chapter_count'] or 0)
                preserved_count = max(existing_count, local_count) if existing['source_toc_url'] else local_count
                # Update existing novel
                cursor.execute('''
                    UPDATE novels 
                    SET chapter_count = ?, last_updated = ?, data_path = ?
                    WHERE slug = ?
                ''', (preserved_count, novel['last_updated'], 
                      novel['data_path'], novel['slug']))
            else:
                # Insert new novel
                cursor.execute('''
                    INSERT INTO novels (slug, title, description, genres, chapter_count, data_path, source_toc_url, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (novel['slug'], novel['title'], novel['description'],
                      novel['genres'], novel['chapter_count'], novel['data_path'],
                      novel.get('source_toc_url'),
                      novel['last_updated']))
    
    return len(novels)


def upsert_novel_record(
    *,
    slug: str,
    title: str,
    description: Optional[str],
    genres: Optional[str],
    data_path: str,
    source_toc_url: Optional[str],
    cover_url: Optional[str] = None,
    chapter_count: Optional[int] = None,
) -> dict:
    last_updated = datetime.utcnow()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM novels WHERE slug = ?", (slug,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE novels
                SET title = ?, description = ?, cover_url = ?, genres = ?,
                    chapter_count = COALESCE(?, chapter_count),
                    data_path = ?, source_toc_url = COALESCE(?, source_toc_url),
                    last_updated = ?
                WHERE slug = ?
                """,
                (
                    title,
                    description,
                    cover_url,
                    genres,
                    chapter_count,
                    data_path,
                    source_toc_url,
                    last_updated,
                    slug,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO novels
                    (slug, title, description, cover_url, genres, chapter_count, data_path, source_toc_url, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    title,
                    description,
                    cover_url,
                    genres,
                    chapter_count or 0,
                    data_path,
                    source_toc_url,
                    last_updated,
                ),
            )

        cursor.execute("SELECT * FROM novels WHERE slug = ?", (slug,))
        return dict_from_row(cursor.fetchone())


@router.get("", response_model=NovelListResponse)
async def list_novels(
    search: Optional[str] = Query(None, description="Search by title"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all novels with optional filtering
    
    FIXED: No longer syncs on every request - use POST /api/novels/sync instead
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM novels WHERE 1=1'
            params = []
            
            if search:
                query += ' AND title LIKE ?'
                params.append(f'%{search}%')
            
            if genre and genre != 'all':
                query += ' AND genres LIKE ?'
                params.append(f'%{genre}%')
            
            query += ' ORDER BY last_updated DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            novels = list_from_rows(cursor.fetchall())
            
            # Get total count
            count_query = 'SELECT COUNT(*) AS count FROM novels WHERE 1=1'
            count_params = []
            if search:
                count_query += ' AND title LIKE ?'
                count_params.append(f'%{search}%')
            if genre and genre != 'all':
                count_query += ' AND genres LIKE ?'
                count_params.append(f'%{genre}%')
            
            cursor.execute(count_query, count_params)
            count_result = cursor.fetchone()
            total = count_result['count'] if hasattr(count_result, 'keys') else count_result[0]
        
        return NovelListResponse(novels=novels, total=total)
    except Exception as e:
        logger.error(f"Database error in list_novels: {e}")
        raise HTTPException(status_code=503, detail=f"Database unavailable: {str(e)}")


@router.delete("/admin/clear-all")
async def clear_all_novels(confirm: str = Body(..., embed=True)):
    """
    DANGER: Delete ALL novels and chapters from database
    
    Use this to reset the database before re-migration.
    This is irreversible!
    
    Requires {"confirm": "DELETE ALL"} in the request body.
    Disabled in production (PostgreSQL) mode.
    """
    if confirm != "DELETE ALL":
        raise HTTPException(
            status_code=400,
            detail='Send {"confirm": "DELETE ALL"} in the request body to confirm this destructive action.',
        )
    if DATABASE_BACKEND != "sqlite":
        raise HTTPException(
            status_code=403,
            detail="Bulk delete is disabled in production. Use database migrations instead.",
        )

    with get_db() as conn:
        cursor = conn.cursor()
        
        # Get counts before deletion
        cursor.execute('SELECT COUNT(*) AS count FROM chapters')
        result = cursor.fetchone()
        chapters_count = result['count'] if hasattr(result, 'keys') else result[0]
        
        cursor.execute('SELECT COUNT(*) AS count FROM novels')
        result = cursor.fetchone()
        novels_count = result['count'] if hasattr(result, 'keys') else result[0]
        
        # Delete chapters first (foreign key)
        cursor.execute('DELETE FROM chapters')
        
        # Delete novels
        cursor.execute('DELETE FROM novels')
        
        logger.warning("Cleared database: %d novels, %d chapters (user-confirmed)", novels_count, chapters_count)
        
        return {
            'message': 'Database cleared successfully',
            'deleted_novels': novels_count,
            'deleted_chapters': chapters_count
        }


@router.get("/{slug}", response_model=NovelResponse)
async def get_novel(slug: str):
    """Get a single novel by slug"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM novels WHERE slug = ?', (slug,))
        novel = dict_from_row(cursor.fetchone())
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
        
        # Increment views
        cursor.execute('UPDATE novels SET views = views + 1 WHERE slug = ?', (slug,))
    
    return novel


@router.post("")
async def create_novel(novel: NovelCreate):
    """Create a new novel (for migration/seeding)"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Check if novel already exists
        cursor.execute('SELECT id FROM novels WHERE slug = ?', (novel.slug,))
        existing = cursor.fetchone()
        
        if existing:
            raise HTTPException(status_code=409, detail="Novel already exists")
        
        cursor.execute('''
            INSERT INTO novels (slug, title, description, cover_url, genres, chapter_count, data_path, source_toc_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (novel.slug, novel.title, novel.description, novel.cover_url, 
              novel.genres, 0, novel.data_path, novel.source_toc_url))
        
        conn.commit()
        
        # Get the created novel
        cursor.execute('SELECT * FROM novels WHERE slug = ?', (novel.slug,))
        created = dict_from_row(cursor.fetchone())
    
    return created


@router.post("/sync")
async def sync_novels():
    """Manually trigger syncing novels from filesystem to database
    
    IMPORTANT: This should be called:
    - Once on application startup
    - After new novels are scraped
    - NOT on every GET request
    """
    try:
        count = sync_novels_to_db()
        return {"message": f"Synced {count} novels from filesystem", "count": count}
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/import-folder")
async def import_novel_folder(
    files: List[UploadFile] = File(...),
    folder_name: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
):
    """Import a local folder of chapter text files into the configured novel output root and sync it to SQLite."""
    text_files = [file for file in files if file.filename and file.filename.lower().endswith(".txt")]
    if not text_files:
        raise HTTPException(status_code=400, detail="No .txt chapter files were uploaded")

    detected_folder_name = folder_name
    if not detected_folder_name:
        first_name = text_files[0].filename.replace("\\", "/")
        first_parts = [part for part in first_name.split("/") if part]
        detected_folder_name = first_parts[0] if len(first_parts) > 1 else Path(first_name).stem

    safe_folder_name = sanitize_folder_name(detected_folder_name or "Imported Novel")
    novel_title = (title or title_from_folder_name(detected_folder_name or safe_folder_name)).strip()
    novel_slug = slugify(novel_title) or slugify(safe_folder_name) or "imported-novel"
    target_dir = DATA_DIR / safe_folder_name
    target_dir.mkdir(parents=True, exist_ok=True)

    parsed_entries = []
    for upload in text_files:
        parsed_entries.append({
            "upload": upload,
            "filename": upload.filename.replace("\\", "/"),
            "parsed_number": parse_uploaded_chapter_number(upload.filename),
        })

    parsed_entries.sort(key=lambda item: (item["parsed_number"] is None, item["parsed_number"] or 10**9, item["filename"].lower()))

    existing = None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, data_path FROM novels WHERE slug = ?", (novel_slug,))
        existing = dict_from_row(cursor.fetchone())
        if existing:
            cursor.execute("DELETE FROM chapters WHERE novel_id = ?", (existing["id"],))

    for existing_file in target_dir.glob("Chapter_*.txt"):
        existing_file.unlink()

    imported_count = 0
    used_numbers = set()
    next_auto_number = 1

    for entry in parsed_entries:
        upload = entry["upload"]
        raw_bytes = await upload.read()
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = raw_bytes.decode("utf-8-sig", errors="ignore")

        chapter_number = entry["parsed_number"]
        if chapter_number is None or chapter_number in used_numbers:
            while next_auto_number in used_numbers:
                next_auto_number += 1
            chapter_number = next_auto_number

        used_numbers.add(chapter_number)
        next_auto_number = max(next_auto_number, chapter_number + 1)

        default_title = chapter_title_from_filename(entry["filename"], chapter_number)
        chapter_title, chapter_body = normalize_uploaded_chapter_content(raw_text, default_title)
        formatted_content = f"{chapter_title}\n============================================================\n\n{chapter_body.strip()}\n"

        chapter_path = target_dir / f"Chapter_{chapter_number:04d}.txt"
        chapter_path.write_text(formatted_content, encoding="utf-8")
        imported_count += 1

    novel_record = upsert_novel_record(
        slug=novel_slug,
        title=novel_title,
        description=f"Imported locally from folder '{safe_folder_name}'",
        genres="Imported,Local",
        data_path=str(target_dir),
        source_toc_url=None,
        chapter_count=imported_count,
    )

    from .chapters import sync_chapters_for_novel

    synced_count = sync_chapters_for_novel(novel_record["id"], str(target_dir))

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE novels
            SET chapter_count = ?, last_updated = ?
            WHERE id = ?
            """,
            (synced_count, datetime.utcnow(), novel_record["id"]),
        )
        cursor.execute("SELECT * FROM novels WHERE id = ?", (novel_record["id"],))
        refreshed = dict_from_row(cursor.fetchone())

    return {
        "message": f"Imported {synced_count} chapters from local folder",
        "novel": refreshed,
        "chapters_imported": synced_count,
        "folder_name": safe_folder_name,
        "replaced_existing": bool(existing),
    }


@router.post("/{slug}/update")
async def update_novel(slug: str, request: Optional[NovelUpdateRequest] = None):
    """Check for missing chapters and scrape them"""
    import threading
    import uuid
    
    # Check if scraper dependencies are available
    from .scraper import check_scraper_available, scrape_jobs, run_scraper_job
    check_scraper_available()  # Returns 503 if deps not installed
    
    from .scraper import NovelScraper
    
    # Get novel from DB
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM novels WHERE slug = ?', (slug,))
        novel = dict_from_row(cursor.fetchone())
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
    
    data_path = Path(novel['data_path']) if novel.get('data_path') else None
    source_toc_url = novel.get('source_toc_url')
    provided_source_toc_url = (request.toc_url or '').strip() if request else ''

    if provided_source_toc_url and provided_source_toc_url != source_toc_url:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE novels
                SET source_toc_url = ?, last_updated = ?
                WHERE slug = ?
                """,
                (provided_source_toc_url, datetime.utcnow(), slug),
            )
        source_toc_url = provided_source_toc_url
        novel['source_toc_url'] = provided_source_toc_url

    if not data_path or not data_path.exists():
        raise HTTPException(status_code=400, detail="Novel data path not found")
    if not source_toc_url:
        raise HTTPException(
            status_code=400,
            detail="Novel source URL not found. Paste the novel TOC URL on the novel page and try again.",
        )
    
    # Get existing chapter numbers from filesystem
    existing_chapters = set()
    for chapter_file in data_path.glob("Chapter_*.txt"):
        match = re.search(r'Chapter_(\d+)', chapter_file.name)
        if match:
            existing_chapters.add(int(match.group(1)))
    
    if not existing_chapters:
        raise HTTPException(status_code=400, detail="No existing chapters found")
    
    try:
        scraper = NovelScraper(headless=True)
        total_chapters = await asyncio.to_thread(scraper.get_total_chapters, source_toc_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect chapters: {str(e)}")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE novels
            SET chapter_count = ?, last_updated = ?
            WHERE slug = ?
            """,
            (total_chapters, datetime.utcnow(), slug),
        )
    
    # Find missing chapters
    all_chapters = set(range(1, total_chapters + 1))
    missing_chapters = sorted(all_chapters - existing_chapters)
    
    if not missing_chapters:
        return {
            "message": "Novel is up to date",
            "total_chapters": total_chapters,
            "local_chapters": len(existing_chapters),
            "missing_chapters": []
        }
    
    # Start scraping job for missing chapters
    job_id = str(uuid.uuid4())
    
    # For now, scrape from first missing to last missing (handles gaps)
    start_chapter = min(missing_chapters)
    end_chapter = max(missing_chapters)
    
    scrape_jobs[job_id] = {
        'status': 'pending',
        'current_chapter': 0,
        'total_chapters': len(missing_chapters),
        'novel_title': novel['title'],
        'persisted': False,
        'error': None
    }
    
    # Start scraper in background
    thread = threading.Thread(
        target=run_scraper_job,
        args=(job_id, source_toc_url, start_chapter, end_chapter, total_chapters),
        daemon=True,
    )
    thread.start()
    
    return {
        "message": f"Started scraping {len(missing_chapters)} missing chapters",
        "job_id": job_id,
        "total_chapters": total_chapters,
        "local_chapters": len(existing_chapters),
        "missing_chapters": missing_chapters[:20]  # Return first 20 for display
    }
