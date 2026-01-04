"""Configuration settings for the audiobook generator."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

OUTPUT_DIRS = {
    'scraped': BASE_DIR / 'data' / 'output',
    'segmented': BASE_DIR / 'Segmentor' / 'output',
    'audio': BASE_DIR / 'audio',
    'logs': BASE_DIR / 'logs'
}

BROWSER_CONFIG = {
    'window_size': '1920,1080',
    'timeout': 15,
    'delay_between_chapters': 2
}

SCRAPER_CONFIG = {
    'min_content_length': 100,
    'max_retries': 3,
    'headless': True
}

SEGMENTATION_CONFIG = {
    'max_chars': 250,
    'min_chars': 120,
    'output_format': 'json'
}

TTS_CONFIG = {
    'sample_rate': 24000,
    'silence_duration': 0.3,
    'default_voice': 'af_heart',
    'use_gpu': True
}

for dir_path in OUTPUT_DIRS.values():
    os.makedirs(dir_path, exist_ok=True)
