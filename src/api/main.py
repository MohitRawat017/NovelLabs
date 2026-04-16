"""
NovelLabs FastAPI backend.
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = Path(os.getenv("NOVELLABS_ENV_FILE", str(BASE_DIR / ".env"))).expanduser()
LOG_DIR = BASE_DIR / "logs" / "backend"
LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 5


class _LoggerPrefixFilter(logging.Filter):
    def __init__(self, prefixes: tuple[str, ...]):
        super().__init__()
        self.prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        return any(record.name.startswith(prefix) for prefix in self.prefixes)


def _configure_logging() -> None:
    if ENV_FILE_PATH.exists():
        load_dotenv(ENV_FILE_PATH, override=True)

    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Reset handlers so reloads do not duplicate outputs.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    console_handler = logging.StreamHandler()
    console_handler.set_name("novellabs_console")
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    app_handler = RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    app_handler.set_name("novellabs_app_file")
    app_handler.setLevel(level)
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)

    audio_handler = RotatingFileHandler(
        LOG_DIR / "audio_progress.log",
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    audio_handler.set_name("novellabs_audio_file")
    audio_handler.setLevel(level)
    audio_handler.setFormatter(formatter)
    audio_handler.addFilter(_LoggerPrefixFilter(("src.api.routes.audio",)))
    root_logger.addHandler(audio_handler)

    error_handler = RotatingFileHandler(
        LOG_DIR / "errors.log",
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    error_handler.set_name("novellabs_error_file")
    error_handler.setLevel(logging.WARNING)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    # Keep terminal readable: suppress request-level access spam.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    root_logger.info(
        "Logging configured (level=%s, directory=%s)",
        level_name,
        LOG_DIR,
    )

_configure_logging()
logger = logging.getLogger(__name__)
logger.info("Starting NovelLabs API...")

from .routes import novels, chapters, scraper, audio
from .database import init_db, close_connection_pool
from .config import (
    ALLOWED_ORIGINS,
    AUDIO_DIR,
    AUTO_SYNC_NOVELS_ON_STARTUP,
    DATABASE_BACKEND,
    LOCAL_DEV_ORIGIN_REGEX,
)

logger.info("Imports completed successfully")

# Initialize FastAPI app
app = FastAPI(
    title="NovelLabs API",
    description="Backend API for the NovelLabs audiobook application",
    version="1.0.0"
)

# CORS configuration - use env var or defaults
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=LOCAL_DEV_ORIGIN_REGEX if DATABASE_BACKEND == "sqlite" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(novels.router, prefix="/api/novels", tags=["novels"])
app.include_router(chapters.router, prefix="/api/chapters", tags=["chapters"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["scraper"])
app.include_router(audio.router, prefix="/api/audio", tags=["audio"])

# Mount static files for covers and audio (only if directories exist)
covers_dir = BASE_DIR / "web" / "public" / "covers"
if covers_dir.exists():
    app.mount("/covers", StaticFiles(directory=str(covers_dir)), name="covers")

audio_dir = Path(AUDIO_DIR)
if audio_dir.exists():
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")


@app.on_event("startup")
async def startup_event():
    """Initialize database and sync local novels."""
    logger.info("Running startup event...")
    try:
        logger.info("Initializing database...")
        init_db()
        logger.info("Database initialized successfully")

        # Reset any chapter_audio rows left stuck in 'generating' or 'paused' from a
        # previous server crash or restart. Without this, the frontend sees them as
        # forever-running or forever-paused with no background thread to service them.
        try:
            from .database import get_db
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE chapter_audio"
                    " SET status = 'cancelled',"
                    "     error  = NULL,"
                    "     progress = 0,"
                    "     updated_at = CURRENT_TIMESTAMP"
                    " WHERE status IN ('generating', 'paused')"
                    "    OR (status = 'failed' AND error = ?)"
                    ,
                    (audio.STALE_RESTART_AUDIO_ERROR,)
                )
                stale_count = cursor.rowcount
            if stale_count:
                logger.warning(
                    "Reset %d stale audio job(s) to 'cancelled' on startup", stale_count
                )
        except Exception as reset_err:
            logger.warning("Could not reset stale generating jobs on startup: %s", reset_err)
        
        # FIXED: Sync novels once on startup instead of on every request.
        if AUTO_SYNC_NOVELS_ON_STARTUP:
            try:
                logger.info("Syncing novels from filesystem...")
                from .routes.novels import sync_novels_to_db
                count = sync_novels_to_db()
                logger.info(f"Synced {count} novels from filesystem")
            except Exception as e:
                logger.error(f"Failed to sync novels on startup: {e}")
                # Don't fail startup if sync fails
        else:
            logger.info("Skipping filesystem sync on startup (AUTO_SYNC_NOVELS_ON_STARTUP=false)")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Don't raise - allow app to start for health checks


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Running shutdown event...")
    try:
        close_connection_pool()
        logger.info("Connection pool closed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "NovelLabs API is running"}


@app.get("/api/health")
async def health_check():
    """Health check for API"""
    return {"status": "healthy"}
