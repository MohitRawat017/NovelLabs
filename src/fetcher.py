"""
HTTP fetch helpers for novel scraping.
"""

from __future__ import annotations

import cloudscraper

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def build_scraper_session() -> cloudscraper.CloudScraper:
    return cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "mobile": False})


def fetch_html(url: str, timeout: int = 30) -> str:
    session = build_scraper_session()
    response = session.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text
