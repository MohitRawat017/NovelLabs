"""
Database module for NovelLabs
PostgreSQL database on Render with SSL, connection pooling, and retry logic
"""

import os
import logging
import time
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from .config import DATABASE_URL

logger = logging.getLogger(__name__)

# Verify PostgreSQL URL
_parsed_url = urlparse(DATABASE_URL)
if _parsed_url.scheme not in ('postgresql', 'postgres'):
    raise ValueError(f"Invalid database URL scheme: {_parsed_url.scheme}. Must be PostgreSQL.")

logger.info(f"Database: PostgreSQL on {_parsed_url.hostname}")

# Import PostgreSQL driver
import psycopg2
import psycopg2.extras
from psycopg2 import pool

# PostgreSQL connection pool
_connection_pool = None


def init_connection_pool():
    """Initialize PostgreSQL connection pool"""
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = psycopg2.pool.SimpleConnectionPool(
                1,  # Min connections
                10, # Max connections
                DATABASE_URL,
                connect_timeout=30,
                sslmode='require',  # CRITICAL: Render requires SSL
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            logger.info("PostgreSQL connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise


def get_connection():
    """Get a database connection with retry logic"""
    # Initialize pool if needed
    if _connection_pool is None:
        init_connection_pool()
    
    # Try to get connection from pool with retry
    max_retries = 3
    for attempt in range(max_retries):
        try:
            conn = _connection_pool.getconn()
            logger.info(f"PostgreSQL connection established (attempt {attempt + 1})")
            return conn
        except Exception as e:
            logger.error(f"PostgreSQL connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise


def return_connection(conn):
    """Return a connection to the pool"""
    if _connection_pool:
        _connection_pool.putconn(conn)


class PostgresCursorWrapper:
    """Wrapper cursor that converts ? placeholders to %s for PostgreSQL"""
    def __init__(self, cursor):
        self._cursor = cursor
    
    def execute(self, query, params=()):
        # Convert ? placeholders to %s
        query = query.replace('?', '%s')
        return self._cursor.execute(query, params)
    
    def fetchone(self):
        return self._cursor.fetchone()
    
    def fetchall(self):
        return self._cursor.fetchall()
    
    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgresConnectionWrapper:
    """Wrapper connection that returns wrapped cursors"""
    def __init__(self, conn):
        self._conn = conn
        self._cursor_factory = psycopg2.extras.RealDictCursor
    
    def cursor(self, *args, **kwargs):
        if 'cursor_factory' not in kwargs:
            kwargs['cursor_factory'] = self._cursor_factory
        return PostgresCursorWrapper(self._conn.cursor(*args, **kwargs))
    
    def commit(self):
        return self._conn.commit()
    
    def rollback(self):
        return self._conn.rollback()
    
    def close(self):
        # Return to pool instead of closing
        if _connection_pool:
            return_connection(self._conn)
        else:
            return self._conn.close()
    
    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = get_connection()
    try:
        conn = PostgresConnectionWrapper(conn)
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def _get_cursor(conn):
    """Get cursor with RealDictCursor factory"""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def db_execute(cursor, query: str, params: tuple = ()):
    """Execute a query with automatic placeholder conversion"""
    query = query.replace('?', '%s')
    cursor.execute(query, params)
    return cursor


def init_db():
    """Initialize the database with required tables"""
    with get_db() as conn:
        cursor = _get_cursor(conn)
        
        # Novels table
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
        
        # Chapters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapters (
                id SERIAL PRIMARY KEY,
                novel_id INTEGER REFERENCES novels(id) ON DELETE CASCADE,
                chapter_number INTEGER NOT NULL,
                title TEXT,
                content TEXT,
                content_path TEXT,
                content_url TEXT,
                audio_path TEXT,
                word_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_id, chapter_number)
            )
        ''')
        
        # Audio segments table (individual TTS chunks)
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
        
        # Full chapter audio table (concatenated audio)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chapter_audio (
                id SERIAL PRIMARY KEY,
                novel_slug TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                voice TEXT DEFAULT 'af_heart',
                status TEXT DEFAULT 'pending',
                audio_url TEXT,
                duration REAL,
                error TEXT,
                progress REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP,
                UNIQUE(novel_slug, chapter_number)
            )
        ''')
        
        # Chunk timing data for karaoke highlighting
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audio_timings (
                id SERIAL PRIMARY KEY,
                novel_slug TEXT NOT NULL,
                chapter_number INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_slug, chapter_number, chunk_index)
            )
        ''')
        
        # User progress table
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
        
        # User preferences table
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
        
        # Insert default preferences if not exists
        cursor.execute('SELECT COUNT(*) FROM user_preferences')
        count_result = cursor.fetchone()
        count = count_result[0] if isinstance(count_result, (list, tuple)) else count_result.get('count', 0)
        
        if count == 0:
            cursor.execute('''
                INSERT INTO user_preferences (font_size) VALUES (18)
            ''')
        
        conn.commit()
        logger.info("PostgreSQL database initialized successfully")


def dict_from_row(row) -> Optional[Dict[str, Any]]:
    """Convert database row to dictionary"""
    if row is None:
        return None
    return dict(row)


def list_from_rows(rows) -> List[Dict[str, Any]]:
    """Convert list of database rows to list of dictionaries"""
    return [dict(row) for row in rows]


def execute_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a query and return results as list of dicts"""
    with get_db() as conn:
        cursor = _get_cursor(conn)
        query = query.replace('?', '%s')
        cursor.execute(query, params)
        return list_from_rows(cursor.fetchall())


def execute_insert(query: str, params: tuple = ()) -> int:
    """Execute an insert and return the last row id"""
    with get_db() as conn:
        cursor = _get_cursor(conn)
        query = query.replace('?', '%s')
        # Add RETURNING id for PostgreSQL
        if 'RETURNING' not in query.upper():
            query = query.rstrip(';') + ' RETURNING id'
        cursor.execute(query, params)
        result = cursor.fetchone()
        return result['id'] if result else 0


def close_connection_pool():
    """Close all connections in the pool (call on shutdown)"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        logger.info("PostgreSQL connection pool closed")
