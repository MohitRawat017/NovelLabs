"""
NovelLabs Backend Services

Audio generation and processing services.
"""

# Optional imports - these may not be used if routes/audio.py is primary
try:
    from .audio_generation import (
        generate_chapter_audio,
        AudioGenerationError,
        segment_chapter_text
    )
    __all__ = [
        "generate_chapter_audio",
        "AudioGenerationError", 
        "segment_chapter_text"
    ]
except ImportError:
    # audio_generation module not available or has import errors
    __all__ = []
