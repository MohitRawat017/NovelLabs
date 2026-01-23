"""
Database module for NovelLabs
Uses SQLite for storing novel metadata and user preferences
"""

import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

# Database path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "novels.db"


def get_connection() -> sqlite3.Connection:
    """Get a database connection"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def init_db():
    """Initialize the database with required tables"""
    os.makedirs(DB_PATH.parent, exist_ok=True)
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Novels table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS novels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                cover_url TEXT,
                genres TEXT,
                views INTEGER DEFAULT 0,
                chapter_count INTEGER DEFAULT 0,
                data_path TEXT,
                last_updated DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Chapters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id INTEGER REFERENCES novels(id) ON DELETE CASCADE,
                chapter_number INTEGER NOT NULL,
                title TEXT,
                content_path TEXT,
                audio_path TEXT,
                word_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_id, chapter_number)
            )
        ''')
        
        # User progress table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id INTEGER REFERENCES novels(id) ON DELETE CASCADE,
                last_chapter INTEGER DEFAULT 0,
                scroll_position REAL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_id)
            )
        ''')
        
        # User preferences table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                font_size INTEGER DEFAULT 18,
                font_family TEXT DEFAULT 'Georgia',
                text_color TEXT DEFAULT '#ffffff',
                bg_color TEXT DEFAULT '#0a0a0f',
                tts_voice TEXT DEFAULT 'af_heart',
                tts_speed REAL DEFAULT 1.0
            )
        ''')
        
        # Insert default preferences if not exists
        cursor.execute('SELECT COUNT(*) FROM user_preferences')
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO user_preferences DEFAULT VALUES
            ''')
        
        print("[INFO] Database initialized successfully")


def dict_from_row(row) -> Optional[Dict[str, Any]]:
    """Convert sqlite3.Row to dictionary"""
    if row is None:
        return None
    return dict(row)


def list_from_rows(rows) -> List[Dict[str, Any]]:
    """Convert list of sqlite3.Row to list of dictionaries"""
    return [dict(row) for row in rows]
