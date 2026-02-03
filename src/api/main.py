"""
NovelLabs FastAPI Backend
Main application entry point
"""

import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Configure logging early
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Starting NovelLabs API...")

from .routes import novels, chapters, scraper, audio
from .database import init_db
from .config import ALLOWED_ORIGINS

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
    """Initialize database on startup"""
    logger.info("Running startup event...")
    try:
        logger.info("Initializing database...")
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Don't raise - allow app to start for health checks


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "NovelLabs API is running"}


@app.get("/api/health")
async def health_check():
    """Health check for API"""
    return {"status": "healthy"}
