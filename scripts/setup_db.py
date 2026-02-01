"""
Database setup script - creates all tables including segments
"""
import sqlite3
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "novels.db"

def setup_database():
    """Create all database tables"""
    print(f"Setting up database at: {DB_PATH}")
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Check existing tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing = [r[0] for r in cursor.fetchall()]
    print(f"Existing tables: {existing}")
    
    # Add content column to chapters if not exists
    cursor.execute("PRAGMA table_info(chapters)")
    columns = [r[1] for r in cursor.fetchall()]
    
    if 'content' not in columns:
        print("Adding 'content' column to chapters...")
        cursor.execute("ALTER TABLE chapters ADD COLUMN content TEXT")
    else:
        print("'content' column already exists")
    
    # Create segments table if not exists
    if 'segments' not in existing:
        print("Creating segments table...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id INTEGER NOT NULL,
                segment_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                audio_url VARCHAR(500),
                timing_data JSON,
                status VARCHAR(50) DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_segment_chapter ON segments(chapter_id, segment_index)')
    else:
        print("segments table already exists")
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"Final tables: {tables}")
    
    cursor.execute("SELECT COUNT(*) FROM novels")
    novel_count = cursor.fetchone()[0]
    print(f"Novels in DB: {novel_count}")
    
    conn.close()
    print("Database setup complete!")


if __name__ == "__main__":
    setup_database()
