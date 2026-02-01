"""
Migration Script: Populate segments table from existing timing JSON files
Reads timing data from audio/{slug}/Chapter_XXXX_timing.json and populates segments table
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "audio"
DB_PATH = BASE_DIR / "data" / "novels.db"


def migrate_segments():
    """Populate segments table from existing timing JSON files"""
    
    if not AUDIO_DIR.exists():
        print(f"[ERROR] Audio directory not found: {AUDIO_DIR}")
        return
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    total_segments = 0
    total_chapters = 0
    skipped_chapters = 0
    
    # Get all novels with their slugs
    cursor.execute("SELECT id, slug FROM novels")
    novels = cursor.fetchall()
    
    for novel in novels:
        novel_id = novel['id']
        slug = novel['slug']
        
        novel_audio_dir = AUDIO_DIR / slug
        
        if not novel_audio_dir.exists():
            continue
        
        print(f"\n[INFO] Processing novel: {slug}")
        
        # Find all timing JSON files
        timing_files = sorted(novel_audio_dir.glob("Chapter_*_timing.json"))
        
        for timing_file in timing_files:
            try:
                # Extract chapter number from filename
                chapter_num_str = timing_file.stem.split('_')[1]
                chapter_number = int(chapter_num_str)
                
                # Get chapter_id from database
                cursor.execute('''
                    SELECT id FROM chapters 
                    WHERE novel_id = ? AND chapter_number = ?
                ''', (novel_id, chapter_number))
                
                chapter_row = cursor.fetchone()
                if not chapter_row:
                    print(f"  [WARN] Chapter {chapter_number} not found in DB, skipping")
                    skipped_chapters += 1
                    continue
                
                chapter_id = chapter_row['id']
                
                # Check if segments already exist
                cursor.execute('''
                    SELECT COUNT(*) as count FROM segments WHERE chapter_id = ?
                ''', (chapter_id,))
                
                existing_count = cursor.fetchone()['count']
                if existing_count > 0:
                    print(f"  [SKIP] Chapter {chapter_number} already has {existing_count} segments")
                    skipped_chapters += 1
                    continue
                
                # Read timing data
                with open(timing_file, 'r', encoding='utf-8') as f:
                    timing_data = json.load(f)
                
                chunks = timing_data.get('chunks', [])
                
                if not chunks:
                    print(f"  [WARN] No chunks in {timing_file.name}")
                    continue
                
                # Insert segments
                chapter_segments = 0
                for chunk in chunks:
                    segment_index = chunk.get('index', 0)
                    text = chunk.get('text', '')
                    
                    # Build timing_data JSON
                    timing_json = json.dumps({
                        'start': chunk.get('start', 0.0),
                        'end': chunk.get('end', 0.0),
                        'duration': chunk.get('duration', 0.0)
                    })
                    
                    cursor.execute('''
                        INSERT INTO segments 
                        (chapter_id, segment_index, text, timing_data, status, created_at)
                        VALUES (?, ?, ?, ?, 'ready', ?)
                    ''', (
                        chapter_id,
                        segment_index,
                        text,
                        timing_json,
                        datetime.utcnow()
                    ))
                    
                    chapter_segments += 1
                
                total_segments += chapter_segments
                total_chapters += 1
                
                print(f"  [OK] Chapter {chapter_number}: {chapter_segments} segments migrated")
                
                # Commit every chapter for safety
                conn.commit()
                
            except Exception as e:
                print(f"  [ERROR] Failed to process {timing_file.name}: {e}")
                continue
    
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"[DONE] Segment Migration Complete!")
    print(f"  - Chapters migrated: {total_chapters}")
    print(f"  - Total segments inserted: {total_segments}")
    print(f"  - Chapters skipped: {skipped_chapters}")
    print(f"{'='*60}")


if __name__ == "__main__":
    print("=" * 60)
    print("Segment Migration Script")
    print("Populates segments table from existing timing JSON files")
    print("=" * 60)
    
    migrate_segments()