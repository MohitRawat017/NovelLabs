"""
Novels API routes
"""

import os
import re
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List

from ..database import get_db, dict_from_row, list_from_rows
from ..models.schemas import NovelResponse, NovelListResponse, NovelCreate

router = APIRouter()

# Base directory for scraped data
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "output"


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
                slug = folder.name.lower().replace(' ', '-')
                slug = re.sub(r'[^a-z0-9-]', '', slug)
                
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
                    'last_updated': last_updated
                })
    
    return novels


def sync_novels_to_db():
    """Sync filesystem novels to database"""
    novels = scan_novels_from_filesystem()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        for novel in novels:
            # Check if novel exists
            cursor.execute('SELECT id FROM novels WHERE slug = ?', (novel['slug'],))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing novel
                cursor.execute('''
                    UPDATE novels 
                    SET chapter_count = ?, last_updated = ?, data_path = ?
                    WHERE slug = ?
                ''', (novel['chapter_count'], novel['last_updated'], 
                      novel['data_path'], novel['slug']))
            else:
                # Insert new novel
                cursor.execute('''
                    INSERT INTO novels (slug, title, description, genres, chapter_count, data_path, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (novel['slug'], novel['title'], novel['description'],
                      novel['genres'], novel['chapter_count'], novel['data_path'],
                      novel['last_updated']))
    
    return len(novels)


@router.get("", response_model=NovelListResponse)
async def list_novels(
    search: Optional[str] = Query(None, description="Search by title"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """Get all novels with optional filtering"""
    # Sync from filesystem first
    sync_novels_to_db()
    
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
        count_query = 'SELECT COUNT(*) FROM novels WHERE 1=1'
        count_params = []
        if search:
            count_query += ' AND title LIKE ?'
            count_params.append(f'%{search}%')
        if genre and genre != 'all':
            count_query += ' AND genres LIKE ?'
            count_params.append(f'%{genre}%')
        
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]
    
    return NovelListResponse(novels=novels, total=total)


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


@router.post("/sync")
async def sync_novels():
    """Manually trigger syncing novels from filesystem to database"""
    count = sync_novels_to_db()
    return {"message": f"Synced {count} novels from filesystem"}


@router.post("/{slug}/update")
async def update_novel(slug: str):
    """Check for missing chapters and scrape them"""
    import sys
    import threading
    import uuid
    
    # Add scraper to path
    sys.path.insert(0, str(BASE_DIR / "src"))
    from scraper import NovelScraper
    from .scraper import scrape_jobs, run_scraper
    
    # Get novel from DB
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM novels WHERE slug = ?', (slug,))
        novel = dict_from_row(cursor.fetchone())
        
        if not novel:
            raise HTTPException(status_code=404, detail="Novel not found")
    
    data_path = Path(novel['data_path']) if novel.get('data_path') else None
    
    if not data_path or not data_path.exists():
        raise HTTPException(status_code=400, detail="Novel data path not found")
    
    # Get existing chapter numbers from filesystem
    existing_chapters = set()
    for chapter_file in data_path.glob("Chapter_*.txt"):
        match = re.search(r'Chapter_(\d+)', chapter_file.name)
        if match:
            existing_chapters.add(int(match.group(1)))
    
    if not existing_chapters:
        raise HTTPException(status_code=400, detail="No existing chapters found")
    
    # Detect total chapters from website
    novel_name = novel['title'].replace(' ', '-')
    toc_url = f"https://novelhi.com/s/{novel_name}"
    
    try:
        scraper = NovelScraper(headless=True)
        driver = scraper.start_driver()
        try:
            total_chapters = scraper.get_total_chapters(driver, toc_url)
        finally:
            driver.quit()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to detect chapters: {str(e)}")
    
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
        'error': None
    }
    
    # Start scraper in background
    thread = threading.Thread(
        target=run_scraper,
        args=(job_id, toc_url, start_chapter, end_chapter)
    )
    thread.start()
    
    return {
        "message": f"Started scraping {len(missing_chapters)} missing chapters",
        "job_id": job_id,
        "total_chapters": total_chapters,
        "local_chapters": len(existing_chapters),
        "missing_chapters": missing_chapters[:20]  # Return first 20 for display
    }

