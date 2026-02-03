"""
NovelLabs FastAPI Backend
Main application entry point
FIXED: Sync novels once on startup + added shutdown handler for connection pool
Added: TTS service wake-up on startup (double-wake strategy)
"""
import os
import logging
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Configure logging early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Starting NovelLabs API...")

from .routes import novels, chapters, scraper, audio
from .database import init_db, close_connection_pool
from .config import ALLOWED_ORIGINS, TTS_SERVICE_URL

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
BASE_DIR = Path(__file__).resolve().parent.parent.parent
covers_dir = BASE_DIR / "web" / "public" / "covers"
if covers_dir.exists():
    app.mount("/covers", StaticFiles(directory=str(covers_dir)), name="covers")

audio_dir = BASE_DIR / "audio"
if audio_dir.exists():
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")


@app.on_event("startup")
async def startup_event():
    """Initialize database, sync novels, and wake up TTS service"""
    logger.info("Running startup event...")
    try:
        logger.info("Initializing database...")
        init_db()
        logger.info("Database initialized successfully")
        
        # FIXED: Sync novels once on startup instead of on every request
        try:
            logger.info("Syncing novels from filesystem...")
            from .routes.novels import sync_novels_to_db
            count = sync_novels_to_db()
            logger.info(f"Synced {count} novels from filesystem")
        except Exception as e:
            logger.error(f"Failed to sync novels on startup: {e}")
            # Don't fail startup if sync fails
        
        # Double-wake strategy: Wake up Lightning AI TTS service
        # This runs async in background - don't block startup
        try:
            logger.info(f"Pinging TTS service at {TTS_SERVICE_URL}...")
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{TTS_SERVICE_URL}/", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"TTS service responded: model_loaded={data.get('model_loaded')}")
                else:
                    logger.warning(f"TTS service returned {response.status_code}")
        except httpx.ConnectError:
            logger.warning(f"TTS service not reachable at {TTS_SERVICE_URL} (may be sleeping)")
        except httpx.ReadTimeout:
            logger.info("TTS service is waking up (timeout expected)")
        except Exception as e:
            logger.warning(f"Could not ping TTS service: {e}")
        
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