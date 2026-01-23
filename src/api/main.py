"""
NovelLabs FastAPI Backend
Main application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .routes import novels, chapters, scraper, audio
from .database import init_db

# Initialize FastAPI app
app = FastAPI(
    title="NovelLabs API",
    description="Backend API for the NovelLabs audiobook application",
    version="1.0.0"
)

# CORS configuration for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(novels.router, prefix="/api/novels", tags=["novels"])
app.include_router(chapters.router, prefix="/api/chapters", tags=["chapters"])
app.include_router(scraper.router, prefix="/api/scraper", tags=["scraper"])
app.include_router(audio.router, prefix="/api/audio", tags=["audio"])

# Mount static files for covers and audio
BASE_DIR = Path(__file__).resolve().parent.parent.parent
app.mount("/covers", StaticFiles(directory=str(BASE_DIR / "web" / "public" / "covers")), name="covers")
app.mount("/audio", StaticFiles(directory=str(BASE_DIR / "audio")), name="audio")


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()


@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "NovelLabs API is running"}


@app.get("/api/health")
async def health_check():
    """Health check for API"""
    return {"status": "healthy"}
