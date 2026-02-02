"""
Novel Migration Script

Uploads local novels from data/output/ to the production PostgreSQL database via API.
Run this locally to populate your Render-hosted database.

Usage:
    python migrate_novels.py

Environment:
    Set API_URL if needed (defaults to production Render URL)
"""

import os
import re
import json
import time
import httpx
from pathlib import Path
from typing import Optional

# Configuration
API_URL = os.getenv("API_URL", "https://novellabs.onrender.com/api")
DATA_DIR = Path(__file__).parent / "data" / "output"

# Rate limiting
DELAY_BETWEEN_CHAPTERS = 0.1  # seconds


def get_novels_from_filesystem():
    """Scan local data/output directory for novels"""
    novels = []
    
    if not DATA_DIR.exists():
        print(f"[ERROR] Data directory not found: {DATA_DIR}")
        return novels
    
    for folder in DATA_DIR.iterdir():
        if folder.is_dir() and not folder.name.startswith('.'):
            chapter_files = sorted(folder.glob("Chapter_*.txt"))
            chapter_count = len(chapter_files)
            
            if chapter_count > 0:
                slug = folder.name.lower().replace(' ', '-')
                slug = re.sub(r'[^a-z0-9-]', '', slug)
                
                novels.append({
                    'folder': folder,
                    'slug': slug,
                    'title': folder.name.replace('-', ' ').title(),
                    'chapter_count': chapter_count,
                    'chapter_files': chapter_files
                })
                print(f"[FOUND] {folder.name}: {chapter_count} chapters")
    
    return novels


def read_chapter(filepath: Path) -> tuple[str, str, int]:
    """Read chapter file and extract title and content"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    title = lines[0].strip() if lines else "Untitled Chapter"
    
    # Skip title and separator line
    body = '\n'.join(lines[2:]).strip() if len(lines) > 2 else content
    word_count = len(body.split())
    
    return title, body, word_count


def upload_novel(client: httpx.Client, novel: dict) -> Optional[int]:
    """Upload novel metadata to API, return novel ID"""
    payload = {
        "slug": novel['slug'],
        "title": novel['title'],
        "description": f"Novel with {novel['chapter_count']} chapters",
        "genres": "Fantasy,Action",
        "chapter_count": novel['chapter_count']
    }
    
    try:
        # Try to create new novel
        response = client.post(f"{API_URL}/novels", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Created novel: {novel['title']}")
            return data.get('id')
        elif response.status_code == 409:
            # Already exists, get existing
            print(f"[EXISTS] Novel already exists: {novel['title']}")
            response = client.get(f"{API_URL}/novels/{novel['slug']}")
            if response.status_code == 200:
                return response.json().get('id')
        else:
            print(f"[ERROR] Failed to create novel: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[ERROR] Exception creating novel: {e}")
    
    return None


def upload_chapters(client: httpx.Client, novel: dict, novel_id: int, limit: Optional[int] = None):
    """Upload chapters for a novel"""
    chapter_files = novel['chapter_files']
    
    if limit:
        chapter_files = chapter_files[:limit]
    
    total = len(chapter_files)
    success = 0
    skip = 0
    fail = 0
    
    print(f"\n[INFO] Uploading {total} chapters for {novel['title']}...")
    
    for i, filepath in enumerate(chapter_files, 1):
        # Extract chapter number from filename
        match = re.search(r'Chapter_(\d+)', filepath.name)
        if not match:
            continue
        
        chapter_number = int(match.group(1))
        
        # Read chapter content
        title, content, word_count = read_chapter(filepath)
        
        payload = {
            "novel_slug": novel['slug'],
            "chapter_number": chapter_number,
            "title": title,
            "content": content,
            "word_count": word_count
        }
        
        try:
            response = client.post(f"{API_URL}/chapters", json=payload, timeout=30)
            
            if response.status_code == 200:
                success += 1
            elif response.status_code == 409:
                skip += 1  # Already exists
            else:
                fail += 1
                if fail <= 3:  # Only show first few errors
                    print(f"[ERROR] Chapter {chapter_number}: {response.status_code}")
        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"[ERROR] Chapter {chapter_number}: {e}")
        
        # Progress
        if i % 100 == 0 or i == total:
            print(f"  Progress: {i}/{total} (ok:{success} skip:{skip} fail:{fail})")
        
        time.sleep(DELAY_BETWEEN_CHAPTERS)
    
    print(f"[DONE] {novel['title']}: {success} uploaded, {skip} skipped, {fail} failed")


def main():
    print("=" * 60)
    print("       NOVEL MIGRATION - Local to PostgreSQL")
    print("=" * 60)
    print(f"API URL: {API_URL}")
    print(f"Data Dir: {DATA_DIR}")
    print()
    
    novels = get_novels_from_filesystem()
    
    if not novels:
        print("[ERROR] No novels found to migrate")
        return
    
    print(f"\n[INFO] Found {len(novels)} novels to migrate")
    
    # Ask for confirmation
    response = input("\nProceed with migration? (y/n): ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        return
    
    # Optional: limit chapters per novel (for testing)
    limit_input = input("Limit chapters per novel? (enter number or 'all'): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else None
    
    with httpx.Client(timeout=60) as client:
        for novel in novels:
            print(f"\n{'='*60}")
            print(f"Processing: {novel['title']}")
            print(f"{'='*60}")
            
            novel_id = upload_novel(client, novel)
            
            if novel_id:
                upload_chapters(client, novel, novel_id, limit=limit)
            else:
                print(f"[SKIP] Could not get novel ID, skipping chapters")
    
    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
