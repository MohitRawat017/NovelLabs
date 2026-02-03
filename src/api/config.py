"""
NovelLabs Backend Configuration

Environment-based configuration for the FastAPI backend on Render.
"""

import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== TTS Service ====================

# Lightning AI TTS service URL
TTS_SERVICE_URL = os.getenv("TTS_SERVICE_URL", "http://localhost:8002")

# Timeout for TTS requests (seconds)
TTS_TIMEOUT = int(os.getenv("TTS_TIMEOUT", "30"))

# ==================== Database ====================

# PostgreSQL on Render (required - no SQLite fallback)
# Render uses postgres:// but psycopg2 expects postgresql://
_db_url = os.getenv("DATABASE_URL")
if not _db_url:
    raise ValueError("DATABASE_URL environment variable is required")
DATABASE_URL = _db_url.replace("postgres://", "postgresql://", 1) if _db_url.startswith("postgres://") else _db_url

logger.info(f"Database URL configured (scheme: {_db_url.split('://')[0] if '://' in _db_url else 'unknown'})")

# ==================== Audio Storage ====================

# cloud = Cloudflare R2 (production)
# local = Local filesystem (development only)
AUDIO_STORAGE_BACKEND = os.getenv("AUDIO_STORAGE_BACKEND", "cloud")

# Audio files are stored per-segment. No concatenated chapter audio.
# This is just for backward compatibility during migration
AUDIO_DIR = os.getenv("AUDIO_DIR", "audio")

# ==================== R2 Audio Storage (Backend) ====================
# The backend needs R2 credentials to upload concatenated chapter audio

R2_AUDIO_ACCOUNT_ID = os.getenv("R2_AUDIO_ACCOUNT_ID", "")
R2_AUDIO_ACCESS_KEY_ID = os.getenv("R2_AUDIO_ACCESS_KEY_ID", "")
R2_AUDIO_SECRET_ACCESS_KEY = os.getenv("R2_AUDIO_SECRET_ACCESS_KEY", "")
R2_AUDIO_BUCKET_NAME = os.getenv("R2_AUDIO_BUCKET_NAME", "novellabs-audio")
R2_AUDIO_PUBLIC_URL = os.getenv("R2_AUDIO_PUBLIC_URL", "")

# ==================== CORS ====================

# Comma-separated list of allowed origins
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", 
    "http://localhost:5173,http://localhost:3000"
).split(",")

# ==================== Logging ====================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# ==================== Phase 2: Background Jobs ====================

# TODO: Redis/Celery integration for durable background jobs
# REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
#
# from celery import Celery
# celery_app = Celery('novellabs', broker=REDIS_URL)
#
# @celery_app.task
# def generate_audio_task(novel_slug, chapter_number, voice):
#     """Durable background job for TTS generation."""
#     pass
