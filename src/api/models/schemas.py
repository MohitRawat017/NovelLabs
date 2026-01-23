"""
Pydantic models for API request/response schemas
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# Novel schemas
class NovelBase(BaseModel):
    title: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    genres: Optional[str] = None  # Comma-separated genres


class NovelCreate(NovelBase):
    slug: str
    data_path: Optional[str] = None


class NovelResponse(NovelBase):
    id: int
    slug: str
    views: int
    chapter_count: int
    data_path: Optional[str]
    last_updated: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


class NovelListResponse(BaseModel):
    novels: List[NovelResponse]
    total: int


# Chapter schemas
class ChapterBase(BaseModel):
    chapter_number: int
    title: Optional[str] = None


class ChapterResponse(ChapterBase):
    id: int
    novel_id: int
    content_path: Optional[str]
    audio_path: Optional[str]
    word_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class ChapterContentResponse(BaseModel):
    id: int
    novel_id: int
    chapter_number: int
    title: str
    content: str
    has_audio: bool
    prev_chapter: Optional[int]
    next_chapter: Optional[int]


class ChapterListResponse(BaseModel):
    chapters: List[ChapterResponse]
    total: int


# Scraper schemas
class ScrapeRequest(BaseModel):
    toc_url: str
    start_chapter: int
    end_chapter: Optional[int] = None  # None triggers auto-detection


class ScrapeStatusResponse(BaseModel):
    status: str  # 'pending', 'running', 'completed', 'failed'
    current_chapter: int
    total_chapters: int
    novel_title: Optional[str]
    error: Optional[str] = None


# User preferences
class UserPreferencesBase(BaseModel):
    font_size: int = 18
    font_family: str = "Georgia"
    text_color: str = "#ffffff"
    bg_color: str = "#0a0a0f"
    tts_voice: str = "af_heart"
    tts_speed: float = 1.0


class UserPreferencesResponse(UserPreferencesBase):
    id: int
    
    class Config:
        from_attributes = True


# User progress
class UserProgressUpdate(BaseModel):
    last_chapter: int
    scroll_position: float = 0


class UserProgressResponse(BaseModel):
    novel_id: int
    last_chapter: int
    scroll_position: float
    updated_at: datetime
    
    class Config:
        from_attributes = True
