"""
NovelLabs backend configuration.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
ENV_FILE_PATH = Path(os.getenv("NOVELLABS_ENV_FILE", str(BASE_DIR / ".env"))).expanduser()

if ENV_FILE_PATH.exists():
    load_dotenv(ENV_FILE_PATH, override=True)
    logger.info("Loaded environment from %s", ENV_FILE_PATH)


def _get_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _parse_csv_env(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]

# ==================== Database ====================

DATABASE_BACKEND = os.getenv("DATABASE_BACKEND", "sqlite").strip().lower()
if DATABASE_BACKEND not in {"sqlite", "postgres"}:
    raise ValueError("DATABASE_BACKEND must be either 'sqlite' or 'postgres'")

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", str(DATA_DIR / "app.db"))
NOVEL_OUTPUT_DIR = Path(os.getenv("NOVEL_OUTPUT_DIR", str(DATA_DIR / "output"))).expanduser()
if not NOVEL_OUTPUT_DIR.is_absolute():
    NOVEL_OUTPUT_DIR = (BASE_DIR / NOVEL_OUTPUT_DIR).resolve()
else:
    NOVEL_OUTPUT_DIR = NOVEL_OUTPUT_DIR.resolve()
DATABASE_URL = ""

if DATABASE_BACKEND == "postgres":
    _db_url = os.getenv("DATABASE_URL")
    if not _db_url:
        raise ValueError("DATABASE_URL environment variable is required when DATABASE_BACKEND=postgres")
    DATABASE_URL = (
        _db_url.replace("postgres://", "postgresql://", 1)
        if _db_url.startswith("postgres://")
        else _db_url
    )
    logger.info("Database configured for PostgreSQL")
else:
    logger.info("Database configured for SQLite at %s", SQLITE_DB_PATH)

# ==================== TTS ====================

SUPPORTED_TTS_PROVIDERS = {"kokoro", "qwen3", "elevenlabs"}
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "kokoro").strip().lower()
if TTS_PROVIDER not in SUPPORTED_TTS_PROVIDERS:
    raise ValueError("TTS_PROVIDER must be one of: kokoro, qwen3, elevenlabs")

TTS_DEVICE = os.getenv("TTS_DEVICE", "auto").strip().lower()
if TTS_DEVICE not in {"auto", "cuda", "cpu"}:
    raise ValueError("TTS_DEVICE must be one of: auto, cuda, cpu")

TTS_VOICE = os.getenv("TTS_VOICE", "af_heart")
TTS_VOICE_PROFILE_DIR = os.getenv("TTS_VOICE_PROFILE_DIR", str(DATA_DIR / "tts_profiles"))

# ==================== Local Qwen3 service ====================

QWEN_TTS_BASE_URL = os.getenv("QWEN_TTS_BASE_URL", "http://localhost:8000").rstrip("/")
QWEN_TTS_MODEL = os.getenv("QWEN_TTS_MODEL", "Qwen/Qwen3-TTS-12Hz-0.6B-Base")
QWEN_TTS_API_STYLE = os.getenv("QWEN_TTS_API_STYLE", "demo").strip().lower()
if QWEN_TTS_API_STYLE not in {"demo", "openai"}:
    raise ValueError("QWEN_TTS_API_STYLE must be one of: demo, openai")

QWEN_TTS_TIMEOUT = float(os.getenv("QWEN_TTS_TIMEOUT", "180"))
QWEN_TTS_LANGUAGE = os.getenv("QWEN_TTS_LANGUAGE", "English")

# ==================== ElevenLabs ====================

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io").rstrip("/")
ELEVENLABS_MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()
ELEVENLABS_OUTPUT_FORMAT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_24000").strip()
ELEVENLABS_TIMEOUT = float(os.getenv("ELEVENLABS_TIMEOUT", "180"))
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()

# ==================== Audio Storage ====================

_configured_audio_storage_backend = os.getenv(
    "AUDIO_STORAGE_BACKEND",
    "local" if DATABASE_BACKEND == "sqlite" else "cloud",
).strip().lower()
AUDIO_STORAGE_BACKEND = (
    "local"
    if DATABASE_BACKEND == "sqlite"
    else _configured_audio_storage_backend
)
if DATABASE_BACKEND == "sqlite" and _configured_audio_storage_backend != "local":
    logger.info("Ignoring AUDIO_STORAGE_BACKEND=%s because SQLite mode is local-only", _configured_audio_storage_backend)
AUDIO_DIR = os.getenv("AUDIO_DIR", str(BASE_DIR / "audio"))

# ==================== R2 Audio Storage (optional in local mode) ====================

R2_AUDIO_ACCOUNT_ID = os.getenv("R2_AUDIO_ACCOUNT_ID", "")
R2_AUDIO_ACCESS_KEY_ID = os.getenv("R2_AUDIO_ACCESS_KEY_ID", "")
R2_AUDIO_SECRET_ACCESS_KEY = os.getenv("R2_AUDIO_SECRET_ACCESS_KEY", "")
R2_AUDIO_BUCKET_NAME = os.getenv("R2_AUDIO_BUCKET_NAME", "novellabs-audio")
R2_AUDIO_PUBLIC_URL = os.getenv("R2_AUDIO_PUBLIC_URL", "")

# ==================== CORS ====================

LOCAL_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
LOCAL_DEV_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

configured_origins = _parse_csv_env(
    os.getenv(
        "ALLOWED_ORIGINS",
        ",".join(LOCAL_DEV_ORIGINS),
    )
)

if DATABASE_BACKEND == "sqlite":
    seen = set()
    ALLOWED_ORIGINS = []
    for origin in [*configured_origins, *LOCAL_DEV_ORIGINS]:
        if origin not in seen:
            ALLOWED_ORIGINS.append(origin)
            seen.add(origin)
else:
    ALLOWED_ORIGINS = configured_origins

# ==================== Logging ====================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
AUTO_SYNC_NOVELS_ON_STARTUP = _get_bool_env("AUTO_SYNC_NOVELS_ON_STARTUP", True)

# ==================== Scraper ====================

SCRAPER_ENABLED = _get_bool_env("SCRAPER_ENABLED", False)
