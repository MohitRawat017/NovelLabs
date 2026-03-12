"""SQLAlchemy models for NovelLabs (legacy reference)."""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, 
    ForeignKey, Index, JSON, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Novel(Base):
    """Novel metadata table"""
    __tablename__ = 'novels'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    cover_url = Column(String(500))
    genres = Column(String(500))  # Comma-separated
    views = Column(Integer, default=0)
    chapter_count = Column(Integer, default=0)
    data_path = Column(String(500))
    last_updated = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    chapters = relationship("Chapter", back_populates="novel", cascade="all, delete-orphan")
    

class Chapter(Base):
    """Chapter table with content storage"""
    __tablename__ = 'chapters'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey('novels.id', ondelete='CASCADE'), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    title = Column(String(500))
    content = Column(Text)  # Full chapter text stored in DB
    content_path = Column(String(500))  # Legacy: path to txt file
    content_url = Column(String(500))  # R2 URL for chapter content
    audio_path = Column(String(500))  # Legacy: path to audio file
    word_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    novel = relationship("Novel", back_populates="chapters")
    segments = relationship("Segment", back_populates="chapter", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_chapter_novel_number', 'novel_id', 'chapter_number', unique=True),
    )


class Segment(Base):
    """Segment table for chunk-level TTS and karaoke"""
    __tablename__ = 'segments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chapter_id = Column(Integer, ForeignKey('chapters.id', ondelete='CASCADE'), nullable=False)
    segment_index = Column(Integer, nullable=False)  # Order within chapter
    text = Column(Text, nullable=False)  # Chunk text
    audio_url = Column(String(500))  # R2 URL after upload
    timing_data = Column(JSON)  # {"start": 0.0, "end": 3.2}
    status = Column(String(50), default='pending')  # pending, processing, ready, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime)  # For lifecycle cleanup
    
    # Relationships
    chapter = relationship("Chapter", back_populates="segments")
    
    __table_args__ = (
        Index('idx_segment_chapter', 'chapter_id', 'segment_index'),
    )


class UserProgress(Base):
    """Track user reading progress"""
    __tablename__ = 'user_progress'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_id = Column(Integer, ForeignKey('novels.id', ondelete='CASCADE'), nullable=False)
    last_chapter = Column(Integer, default=0)
    scroll_position = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_progress_novel', 'novel_id', unique=True),
    )


class UserPreferences(Base):
    """User settings and preferences"""
    __tablename__ = 'user_preferences'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    font_size = Column(Integer, default=18)
    font_family = Column(String(100), default='Georgia')
    text_color = Column(String(20), default='#ffffff')
    bg_color = Column(String(20), default='#0a0a0f')
    tts_voice = Column(String(50), default='af_heart')
    tts_speed = Column(Float, default=1.0)


class ChapterAudio(Base):
    """Full chapter audio (concatenated from segments)"""
    __tablename__ = 'chapter_audio'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_slug = Column(String(255), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    voice = Column(String(50), default='af_heart')
    status = Column(String(50), default='pending')  # pending, generating, completed, failed
    audio_url = Column(String(500), nullable=True)  # R2 URL for final audio
    duration = Column(Float, nullable=True)  # Total duration in seconds
    progress = Column(Integer, default=0)  # 0-100%
    error = Column(Text, nullable=True)  # Error message if failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_chapter_audio_lookup', 'novel_slug', 'chapter_number', unique=True),
    )


class AudioTiming(Base):
    """Chunk timing data for karaoke highlighting"""
    __tablename__ = 'audio_timings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    novel_slug = Column(String(255), nullable=False)
    chapter_number = Column(Integer, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)  # Start time in seconds
    end_time = Column(Float, nullable=False)  # End time in seconds
    text = Column(Text, nullable=False)  # Chunk text
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_audio_timings_lookup', 'novel_slug', 'chapter_number'),
    )


# Legacy database connection helpers
def get_engine(database_url: Optional[str] = None):
    """Legacy SQLAlchemy helper kept only for archival tooling."""
    import os
    if database_url is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable is required")
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    return create_engine(database_url, echo=False)


def get_session(engine=None):
    """Create a session factory"""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()
