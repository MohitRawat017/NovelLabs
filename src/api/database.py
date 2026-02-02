"""
Database module for NovelLabs
Supports both SQLite (local dev) and PostgreSQL (production)
"""

import os
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from .config import DATABASE_URL

logger = logging.getLogger(__name__)

# Determine database type from URL
_parsed_url = urlparse(DATABASE_URL)
IS_POSTGRES = _parsed_url.scheme in ('postgresql', 'postgres')

# Import appropriate database library
if IS_POSTGRES:
    import psycopg2
    import psycopg2.extras
    logger.info("Using PostgreSQL database")
else:
    import sqlite3
    logger.info("Using SQLite database")

# SQLite fallback path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "novels.db"


def get_connection():
    """Get a database connection (SQLite or PostgreSQL)"""
    if IS_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = get_connection()
    try:
        if IS_POSTGRES:
            # Use RealDictCursor for PostgreSQL to get dict-like rows
            conn.cursor_factory = psycopg2.extras.RealDictCursor
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def _get_cursor(conn):
    """Get appropriate cursor for database type"""
    if IS_POSTGRES:
        return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        return conn.cursor()


def db_execute(cursor, query: str, params: tuple = ()):
    """Execute a query with automatic placeholder conversion for PostgreSQL"""
    if IS_POSTGRES:
        # Convert SQLite ? placeholders to PostgreSQL %s
        query = query.replace('?', '%s')
    cursor.execute(query, params)
    return cursor


def init_db():
    """Initialize the database with required tables"""
    if not IS_POSTGRES:
        os.makedirs(DB_PATH.parent, exist_ok=True)
    
    # PostgreSQL uses SERIAL, SQLite uses INTEGER PRIMARY KEY AUTOINCREMENT
    # PostgreSQL uses TIMESTAMP, SQLite uses DATETIME
    # Both support similar syntax for CREATE TABLE IF NOT EXISTS
    
    with get_db() as conn:
        cursor = _get_cursor(conn)
        
        if IS_POSTGRES:
            # PostgreSQL schema
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS novels (
                    id SERIAL PRIMARY KEY,
                    slug TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    cover_url TEXT,
                    genres TEXT,
                    views INTEGER DEFAULT 0,
                    chapter_count INTEGER DEFAULT 0,
                    data_path TEXT,
                    last_updated TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chapters (
                    id SERIAL PRIMARY KEY,
                    novel_id INTEGER REFERENCES novels(id) ON DELETE CASCADE,
                    chapter_number INTEGER NOT NULL,
                    title TEXT,
                    content TEXT,
                    content_path TEXT,
                    audio_path TEXT,
                    word_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(novel_id, chapter_number)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audio_segments (
                    id SERIAL PRIMARY KEY,
                    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    text TEXT,
                    audio_url TEXT,
                    duration REAL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter_id, segment_index)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_progress (
                    id SERIAL PRIMARY KEY,
                    novel_id INTEGER REFERENCES novels(id) ON DELETE CASCADE,
                    last_chapter INTEGER DEFAULT 0,
                    scroll_position REAL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(novel_id)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id SERIAL PRIMARY KEY,
                    font_size INTEGER DEFAULT 18,
                    font_family TEXT DEFAULT 'Georgia',
                    text_color TEXT DEFAULT '#ffffff',
                    bg_color TEXT DEFAULT '#0a0a0f',
                    tts_voice TEXT DEFAULT 'af_heart',
                    tts_speed REAL DEFAULT 1.0
                )
            ''')
        else:
            # SQLite schema
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
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    novel_id INTEGER REFERENCES novels(id) ON DELETE CASCADE,
                    chapter_number INTEGER NOT NULL,
                    title TEXT,
                    content TEXT,
                    content_path TEXT,
                    audio_path TEXT,
                    word_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(novel_id, chapter_number)
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audio_segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
                    segment_index INTEGER NOT NULL,
                    text TEXT,
                    audio_url TEXT,
                    duration REAL,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chapter_id, segment_index)
                )
            ''')
            
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
        count_result = cursor.fetchone()
        count = count_result[0] if isinstance(count_result, (list, tuple)) else count_result.get('count', 0)
        
        if count == 0:
            cursor.execute('''
                INSERT INTO user_preferences (font_size) VALUES (18)
            ''')
        
        conn.commit()
        logger.info(f"Database initialized successfully (PostgreSQL: {IS_POSTGRES})")


def dict_from_row(row) -> Optional[Dict[str, Any]]:
    """Convert database row to dictionary"""
    if row is None:
        return None
    if IS_POSTGRES:
        # RealDictRow is already dict-like
        return dict(row)
    else:
        return dict(row)


def list_from_rows(rows) -> List[Dict[str, Any]]:
    """Convert list of database rows to list of dictionaries"""
    return [dict(row) for row in rows]


def execute_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a query and return results as list of dicts"""
    with get_db() as conn:
        cursor = _get_cursor(conn)
        # Convert ? to %s for PostgreSQL
        if IS_POSTGRES:
            query = query.replace('?', '%s')
        cursor.execute(query, params)
        return list_from_rows(cursor.fetchall())


def execute_insert(query: str, params: tuple = ()) -> int:
    """Execute an insert and return the last row id"""
    with get_db() as conn:
        cursor = _get_cursor(conn)
        if IS_POSTGRES:
            query = query.replace('?', '%s')
            # Add RETURNING id for PostgreSQL
            if 'RETURNING' not in query.upper():
                query = query.rstrip(';') + ' RETURNING id'
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result['id'] if result else 0
        else:
            cursor.execute(query, params)
            return cursor.lastrowid
