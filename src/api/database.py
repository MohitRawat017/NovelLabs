"""Database helpers for NovelLabs (SQLite-first with PostgreSQL compatibility)."""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from .config import DATABASE_BACKEND, DATABASE_URL, SQLITE_DB_PATH

logger = logging.getLogger(__name__)

_connection_pool = None
psycopg2 = None
psycopg2_extras = None

if DATABASE_BACKEND == "postgres":
    import psycopg2 as _psycopg2
    import psycopg2.extras as _psycopg2_extras
    from psycopg2 import pool

    psycopg2 = _psycopg2
    psycopg2_extras = _psycopg2_extras

    parsed = urlparse(DATABASE_URL)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"Invalid database URL scheme: {parsed.scheme}")
    logger.info("Database backend: PostgreSQL on %s", parsed.hostname)
else:
    logger.info("Database backend: SQLite at %s", SQLITE_DB_PATH)


def _convert_placeholders(query: str) -> str:
    return query.replace("?", "%s") if DATABASE_BACKEND == "postgres" else query


def _sqlite_connect() -> sqlite3.Connection:
    db_path = Path(SQLITE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_connection_pool() -> None:
    global _connection_pool

    if DATABASE_BACKEND != "postgres" or _connection_pool is not None:
        return

    _connection_pool = pool.SimpleConnectionPool(
        1,
        10,
        DATABASE_URL,
        connect_timeout=30,
        sslmode="require",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    logger.info("PostgreSQL connection pool initialized")


def get_connection():
    if DATABASE_BACKEND == "sqlite":
        return _sqlite_connect()

    if _connection_pool is None:
        init_connection_pool()

    max_retries = 3
    for attempt in range(max_retries):
        try:
            return _connection_pool.getconn()
        except Exception as exc:
            logger.error("PostgreSQL connection attempt %s failed: %s", attempt + 1, exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)


def return_connection(conn) -> None:
    if DATABASE_BACKEND == "postgres" and _connection_pool is not None:
        _connection_pool.putconn(conn)


class CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=()):
        return self._cursor.execute(_convert_placeholders(query), params)

    def executemany(self, query, seq_of_params):
        return self._cursor.executemany(_convert_placeholders(query), seq_of_params)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class ConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        if DATABASE_BACKEND == "postgres" and "cursor_factory" not in kwargs:
            kwargs["cursor_factory"] = psycopg2_extras.RealDictCursor
        return CursorWrapper(self._conn.cursor(*args, **kwargs))

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        if DATABASE_BACKEND == "postgres":
            return_connection(self._conn)
        else:
            self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


@contextmanager
def get_db():
    conn = ConnectionWrapper(get_connection())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _schema_statements() -> List[str]:
    id_type = "SERIAL PRIMARY KEY" if DATABASE_BACKEND == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"

    return [
        f"""
        CREATE TABLE IF NOT EXISTS novels (
            id {id_type},
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            cover_url TEXT,
            genres TEXT,
            views INTEGER DEFAULT 0,
            chapter_count INTEGER DEFAULT 0,
            data_path TEXT,
            source_toc_url TEXT,
            last_updated TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS chapters (
            id {id_type},
            novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
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
        """,
        f"""
        CREATE TABLE IF NOT EXISTS audio_segments (
            id {id_type},
            chapter_id INTEGER REFERENCES chapters(id) ON DELETE CASCADE,
            segment_index INTEGER NOT NULL,
            text TEXT,
            audio_url TEXT,
            duration REAL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chapter_id, segment_index)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS chapter_audio (
            id {id_type},
            novel_slug TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            provider TEXT DEFAULT 'kokoro',
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
        """,
        f"""
        CREATE TABLE IF NOT EXISTS audio_timings (
            id {id_type},
            novel_slug TEXT NOT NULL,
            chapter_number INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            start_time REAL NOT NULL,
            end_time REAL NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(novel_slug, chapter_number, chunk_index)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS novel_tts_profiles (
            id {id_type},
            novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
            provider TEXT NOT NULL,
            voice_name TEXT,
            display_name TEXT,
            ref_audio_path TEXT,
            ref_text TEXT,
            language TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE(novel_id, provider)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS user_progress (
            id {id_type},
            novel_id INTEGER REFERENCES novels(id) ON DELETE CASCADE,
            last_chapter INTEGER DEFAULT 0,
            scroll_position REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(novel_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id {id_type},
            font_size INTEGER DEFAULT 18,
            font_family TEXT DEFAULT 'Georgia',
            text_color TEXT DEFAULT '#ffffff',
            bg_color TEXT DEFAULT '#0a0a0f',
            tts_voice TEXT DEFAULT 'af_heart',
            tts_speed REAL DEFAULT 1.0
        )
        """,
    ]


def _ensure_column(cursor, table: str, column: str, definition: str) -> None:
    if DATABASE_BACKEND == "sqlite":
        rows = cursor.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {row["name"] for row in rows}
    else:
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s
            """,
            (table,),
        )
        existing = {row["column_name"] for row in cursor.fetchall()}

    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_db() as conn:
        cursor = conn.cursor()

        for statement in _schema_statements():
            cursor.execute(statement)

        _ensure_column(cursor, "novels", "source_toc_url", "TEXT")
        _ensure_column(cursor, "chapter_audio", "provider", "TEXT DEFAULT 'kokoro'")

        cursor.execute("SELECT COUNT(*) AS count FROM user_preferences")
        row = cursor.fetchone()
        count = row["count"] if row else 0
        if count == 0:
            cursor.execute("INSERT INTO user_preferences (font_size) VALUES (?)", (18,))

    logger.info("Database initialized successfully")


def dict_from_row(row) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    return dict(row)


def list_from_rows(rows: Iterable[Any]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def execute_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return list_from_rows(cursor.fetchall())


def execute_insert(query: str, params: tuple = ()) -> int:
    with get_db() as conn:
        cursor = conn.cursor()
        if DATABASE_BACKEND == "postgres":
            if "RETURNING" not in query.upper():
                query = query.rstrip(";") + " RETURNING id"
            cursor.execute(query, params)
            row = cursor.fetchone()
            return row["id"] if row else 0

        cursor.execute(query, params)
        return cursor.lastrowid


def db_execute(cursor, query: str, params: tuple = ()):
    cursor.execute(query, params)
    return cursor


def close_connection_pool() -> None:
    global _connection_pool
    if DATABASE_BACKEND == "postgres" and _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("PostgreSQL connection pool closed")
