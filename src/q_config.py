# =============================================================================
# QWEN API CONFIGURATION
# =============================================================================

QWEN_API_URL = "http://127.0.0.1:7860"  # Qwen Gradio API endpoint
API_TIMEOUT = 300  # 5 minutes per chunk
MAX_RETRIES = 3  # Retry failed chunks

# =============================================================================
# VOICE GENERATION MODE
# =============================================================================

# Options: "custom_voice", "voice_clone", "voice_design"
VOICE_MODE = "custom_voice"

# =============================================================================
# CUSTOM VOICE SETTINGS (Pre-built speakers)
# =============================================================================
# Use this mode for high-quality pre-built voices
# Best for: General audiobook narration

CUSTOM_VOICE_SPEAKER = "Ryan"  # Options: Aiden, Dylan, Eric, Ono_anna, Ryan, Serena, Sohee, Uncle_fu, Vivian
CUSTOM_VOICE_LANGUAGE = "English"  # Auto, Chinese, English, Japanese, Korean, French, German, Spanish, Portuguese, Russian
CUSTOM_VOICE_INSTRUCT = "Speak naturally and clearly, as if reading a book."  # Style instruction (1.7B only)
CUSTOM_VOICE_MODEL_SIZE = "1.7B"  # 0.6B or 1.7B
CUSTOM_VOICE_SEED = -1  # -1 for auto, or specific seed for consistency

# =============================================================================
# VOICE CLONE SETTINGS (Custom voice from reference audio)
# =============================================================================
# Use this mode to clone a specific voice from a reference audio file
# Best for: Cloning a specific person's voice

VOICE_CLONE_REF_AUDIO = ""  # Path to reference audio file (WAV format)
VOICE_CLONE_REF_TEXT = ""  # Text matching what's spoken in the reference audio
VOICE_CLONE_LANGUAGE = "Auto"
VOICE_CLONE_USE_XVECTOR_ONLY = False  # True for lower quality but faster (no text needed)
VOICE_CLONE_MODEL_SIZE = "1.7B"  # 0.6B or 1.7B
VOICE_CLONE_MAX_CHUNK_CHARS = 200  # Maximum characters per chunk
VOICE_CLONE_CHUNK_GAP = 0  # Gap between chunks in seconds
VOICE_CLONE_SEED = -1  # -1 for auto

# =============================================================================
# VOICE DESIGN SETTINGS (Describe the voice you want)
# =============================================================================
# Use this mode to generate speech with a specific tone/emotion
# Best for: Expressive narration, character voices
# Note: Only available with 1.7B model

VOICE_DESIGN_LANGUAGE = "Auto"
VOICE_DESIGN_DESCRIPTION = "Speak in a clear, professional narrator voice suitable for reading audiobooks."
VOICE_DESIGN_SEED = -1  # -1 for auto

# =============================================================================
# PROCESSING SETTINGS
# =============================================================================

BOOKS_FOLDER = "books_to_convert"  # Input folder for books
CHUNK_SIZE_WORDS = 1200  # Words per chunk (adjust based on your needs)
MAX_WORKERS = 1  # Concurrent chunks (keep at 1 to avoid rate limiting)
MIN_DELAY_BETWEEN_CHUNKS = 2  # Seconds delay between API calls

# =============================================================================
# AUDIO OUTPUT SETTINGS
# =============================================================================

AUDIO_FORMAT = "mp3"  # Output format: mp3, wav, m4a
AUDIO_BITRATE = "128k"  # Audio quality: 64k, 128k, 192k, 256k, 320k

# =============================================================================
# ADVANCED SETTINGS
# =============================================================================

# Supported file extensions
SUPPORTED_FORMATS = ['.txt', '.pdf', '.epub', '.docx', '.doc']

# Text cleaning options
CLEAN_PAGE_NUMBERS = True  # Remove standalone numbers
NORMALIZE_WHITESPACE = True  # Clean up spacing
SENTENCE_BOUNDARY_DETECTION = True  # Smart sentence splitting

# Cache settings
ENABLE_CACHING = True  # Cache processed chunks
CACHE_CLEANUP_DAYS = 30  # Remove cache older than X days

# Logging settings
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True  # Save logs to file
LOG_TO_CONSOLE = True  # Display logs in terminal