"""
Migration Script: Import existing .txt chapter files into database
Reads chapters from data/output/{slug}/*.txt and stores in chapters.content column
"""

import sqlite3
import re
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "output"
DB_PATH = BASE_DIR / "data" / "novels.db"


def extract_chapter_number(filename: str) -> int | None:
    """Extract chapter number from filename like 'Chapter_1495.txt'"""
    match = re.search(r'Chapter[_\s]*(\d+)', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def get_or_create_novel(cursor: sqlite3.Cursor, slug: str, folder_name: str = "") -> int:
    """Get existing novel id or create new one"""
    cursor.execute("SELECT id FROM novels WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    if row:
        return row[0]
    
    # Create new novel entry, use folder_name for nice title if provided
    title = (folder_name or slug).replace('-', ' ').title()
    cursor.execute(
        "INSERT INTO novels (slug, title, data_path) VALUES (?, ?, ?)",
        (slug, title, str(DATA_DIR / folder_name if folder_name else DATA_DIR / slug))
    )
    return cursor.lastrowid or 0


def migrate_chapters():
    """Main migration function"""
    if not DATA_DIR.exists():
        print(f"[ERROR] Data directory not found: {DATA_DIR}")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    total_migrated = 0
    total_skipped = 0
    
    # Process each novel directory
    for novel_dir in DATA_DIR.iterdir():
        if not novel_dir.is_dir():
            continue
        
        # Normalize slug to match novels.py (lowercase, no special chars)
        slug = novel_dir.name.lower().replace(' ', '-')
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        print(f"\n[INFO] Processing novel: {novel_dir.name} (slug: {slug})")
        
        novel_id = get_or_create_novel(cursor, slug, novel_dir.name)
        
        # Get existing chapters with content
        cursor.execute(
            "SELECT chapter_number FROM chapters WHERE novel_id = ? AND content IS NOT NULL",
            (novel_id,)
        )
        existing_with_content = {row[0] for row in cursor.fetchall()}
        
        # Process each chapter file
        chapter_files = sorted(novel_dir.glob("Chapter_*.txt"))
        
        for chapter_file in chapter_files:
            chapter_num = extract_chapter_number(chapter_file.name)
            if chapter_num is None:
                print(f"  [WARN] Could not parse chapter number: {chapter_file.name}")
                continue
            
            # Skip if already has content
            if chapter_num in existing_with_content:
                total_skipped += 1
                continue
            
            # Read content
            try:
                content = chapter_file.read_text(encoding='utf-8')
                word_count = len(content.split())
            except Exception as e:
                print(f"  [ERROR] Failed to read {chapter_file.name}: {e}")
                continue
            
            # Check if chapter record exists
            cursor.execute(
                "SELECT id FROM chapters WHERE novel_id = ? AND chapter_number = ?",
                (novel_id, chapter_num)
            )
            existing = cursor.fetchone()
            
            if existing:
                # Update existing record with content
                cursor.execute(
                    "UPDATE chapters SET content = ?, word_count = ? WHERE id = ?",
                    (content, word_count, existing[0])
                )
            else:
                # Insert new chapter
                cursor.execute('''
                    INSERT INTO chapters (novel_id, chapter_number, title, content, content_path, word_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    novel_id,
                    chapter_num,
                    f"Chapter {chapter_num}",
                    content,
                    str(chapter_file),
                    word_count
                ))
            
            total_migrated += 1
            if total_migrated % 50 == 0:
                print(f"  [INFO] Migrated {total_migrated} chapters...")
                conn.commit()
        
        # Update novel chapter count
        cursor.execute(
            "SELECT COUNT(*) FROM chapters WHERE novel_id = ?",
            (novel_id,)
        )
        chapter_count = cursor.fetchone()[0]
        cursor.execute(
            "UPDATE novels SET chapter_count = ? WHERE id = ?",
            (chapter_count, novel_id)
        )
    
    conn.commit()
    conn.close()
    
    print(f"\n[DONE] Migration complete!")
    print(f"  - Migrated: {total_migrated} chapters")
    print(f"  - Skipped (already had content): {total_skipped}")


if __name__ == "__main__":
    print("=" * 50)
    print("Chapter Content Migration Script")
    print("=" * 50)
    migrate_chapters()
