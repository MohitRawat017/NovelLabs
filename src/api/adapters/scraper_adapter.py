"""Compatibility adapter for the new async scraper package."""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from typing import Dict, Tuple

from src.SCRAPER.scraper import FWNScraper, Settings
from src.SCRAPER.scraper.http_client import HTTPClient
from src.SCRAPER.scraper.parser import FWNParser


class NovelScraper:
    """Expose the legacy sync scraper interface using the new async stack."""

    def __init__(self, headless: bool = True):
        # Preserve legacy constructor contract. The new scraper is HTTP-based.
        self.headless = headless
        self.settings = Settings()
        self._chapter_url_cache: Dict[str, Dict[int, str]] = {}

    def get_novel_name(self, toc_url: str) -> str:
        """Extract novel slug-like name from legacy TOC or chapter URLs."""
        return self._extract_slug(toc_url)

    def get_total_chapters(self, toc_url: str) -> int:
        """Fetch chapter list and return total chapter count."""
        chapter_urls = self._get_chapter_url_map(toc_url)
        if not chapter_urls:
            raise ValueError("No chapters found for the provided novel URL")
        return max(chapter_urls.keys())

    def generate_chapter_urls(self, toc_url: str, start: int, end: int) -> Tuple[list[str], str]:
        """Return resolved chapter URLs for an inclusive chapter range."""
        if start < 1 or end < start:
            raise ValueError("Invalid chapter range requested")

        chapter_url_map = self._get_chapter_url_map(toc_url)
        missing = [number for number in range(start, end + 1) if number not in chapter_url_map]
        if missing:
            if len(missing) == 1:
                raise ValueError(f"Chapter {missing[0]} was not found in the target novel")
            raise ValueError(
                f"Requested chapters are missing from the target novel: {missing[0]} to {missing[-1]}"
            )

        chapter_urls = [chapter_url_map[number] for number in range(start, end + 1)]
        return chapter_urls, self.get_novel_name(toc_url)

    def scrape_chapter(self, chapter_url: str) -> Tuple[str, str]:
        """Scrape a chapter URL and return legacy tuple payload."""
        chapter_number = self._extract_chapter_number(chapter_url)
        return self._run_async(self._scrape_chapter_async(chapter_url, chapter_number))

    def _chapter_cache_key(self, toc_url: str) -> str:
        return self._query_name(toc_url).strip().lower()

    def _get_chapter_url_map(self, toc_url: str) -> Dict[int, str]:
        cache_key = self._chapter_cache_key(toc_url)
        if cache_key not in self._chapter_url_cache:
            self._chapter_url_cache[cache_key] = self._run_async(
                self._fetch_chapter_urls_async(toc_url)
            )
        return self._chapter_url_cache[cache_key]

    async def _fetch_chapter_urls_async(self, toc_url: str) -> Dict[int, str]:
        """Resolve a novel by name and return chapter number -> URL mapping."""
        query_name = self._query_name(toc_url)
        if not query_name:
            raise ValueError("Could not infer novel name from the provided URL")

        async with FWNScraper(self.settings) as scraper:
            report = await scraper.scrape_novel(query_name, dry_run=True)

        chapter_urls = {item.number: item.url for item in report.chapters if item.url and item.number > 0}
        if not chapter_urls:
            raise ValueError(f"No chapters found for novel '{query_name}'")
        return chapter_urls

    async def _scrape_chapter_async(self, chapter_url: str, chapter_number: int) -> Tuple[str, str]:
        parser = FWNParser(base_url=self.settings.BASE_URL)
        async with HTTPClient(self.settings) as client:
            html = await client.get(chapter_url)

        parsed = parser.parse_chapter_content(
            html=html,
            chapter_number=chapter_number,
            chapter_url=chapter_url,
        )
        if parsed is None or not parsed.content.strip():
            raise ValueError("Could not extract chapter content from the target URL")

        if parsed.title.strip():
            title = parsed.title.strip()
        elif chapter_number > 0:
            title = f"Chapter {chapter_number}"
        else:
            title = "Untitled Chapter"

        return title, parsed.content.strip()

    def _query_name(self, toc_url: str) -> str:
        slug = self._extract_slug(toc_url)
        return re.sub(r"[_-]+", " ", slug).strip()

    @staticmethod
    def _extract_slug(toc_url: str) -> str:
        value = toc_url.strip().rstrip("/")
        parsed = urllib.parse.urlparse(value)

        if parsed.scheme and parsed.netloc:
            parts = [part for part in parsed.path.split("/") if part]
            if not parts:
                return value

            candidate = parts[-1]
            if candidate.isdigit() and len(parts) >= 2:
                candidate = parts[-2]
            return urllib.parse.unquote(candidate)

        return value

    @staticmethod
    def _extract_chapter_number(chapter_url: str) -> int:
        match = re.search(r"(?:chapter-|/)(\d+)(?:/)?$", chapter_url)
        return int(match.group(1)) if match else 0

    @staticmethod
    def _run_async(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # Legacy methods are sync and expected to run in worker threads.
        coro.close()
        raise RuntimeError("Sync scraper adapter cannot run inside an active event loop")
