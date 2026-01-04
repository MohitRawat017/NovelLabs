import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "data", "output")
DEFAULT_LOG_DIR = os.path.join(BASE_DIR, "logs")

BROWSER_CONFIG = {
    "window_size": "1920,1080",
    "timeout": 15,
    "delay_between_chapters": 2,
}

SCRAPER_CONFIG = {
    "min_content_length": 100,
    "max_retries": 3,
    "headless": False,
}
