"""
NovelTrust scraper module.

This scraper uses Cloudscraper + BeautifulSoup instead of browser automation.
It extracts NovelTrust list pages, novel detail pages, and chapter content.
"""

from __future__ import annotations

import os
import re
import logging
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

SCRAPER_AVAILABLE = False
BeautifulSoup = None
fetch_html = None

try:
    from bs4 import BeautifulSoup  # type: ignore[assignment]
except ImportError:
    BeautifulSoup = None

try:
    from .fetcher import fetch_html  # type: ignore[assignment]
except ImportError:
    try:
        from fetcher import fetch_html  # type: ignore[assignment]
    except ImportError:
        fetch_html = None

SCRAPER_AVAILABLE = BeautifulSoup is not None and fetch_html is not None


def _check_dependencies():
    if not SCRAPER_AVAILABLE:
        raise ImportError(
            "Scraping dependencies not installed. "
            "Install with: pip install beautifulsoup4 cloudscraper"
        )


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clean_multiline_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in (value or "").splitlines()]
    return "\n\n".join(line for line in lines if line)


def _extract_first_text(soup, selectors: List[str], default: str = "") -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                return text
    return default


def _extract_meta_content(soup, *names: str) -> str:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if node and node.get("content"):
            return _clean_text(node["content"])
    return ""


def _natural_chapter_key(url: str) -> int:
    match = re.search(r"chapter-(\d+)", url)
    return int(match.group(1)) if match else 10**9


class NovelScraper:
    base_domain = "https://noveltrust.com"

    def __init__(self, headless: bool = True):
        _check_dependencies()
        self.headless = headless

    def fetch(self, url: str) -> str:
        logger.info("Fetching %s", url)
        return fetch_html(url)

    def parse_list_page(self, html: str, page_url: str) -> List[dict]:
        soup = BeautifulSoup(html, "html.parser")
        novels = []
        seen = set()

        for anchor in soup.select('a[href*="/novel/"]'):
            href = (anchor.get("href") or "").strip()
            if not href or "/chapter-" in href:
                continue

            absolute_url = urljoin(page_url, href)
            parsed = urlparse(absolute_url)
            if parsed.netloc != urlparse(self.base_domain).netloc:
                continue

            canonical = absolute_url.rstrip("/")
            if canonical in seen:
                continue

            title = _clean_text(anchor.get_text(" ", strip=True))
            if not title:
                title = _clean_text(anchor.get("title", ""))
            if not title:
                title = _clean_text(canonical.rstrip("/").split("/")[-1].replace("-", " "))

            container = anchor.find_parent(["article", "li", "div"]) or anchor
            genres = []
            for genre_anchor in container.select('a[href*="genre"], .genre a, .genres a'):
                genre = _clean_text(genre_anchor.get_text(" ", strip=True))
                if genre and genre not in genres:
                    genres.append(genre)

            rating = _extract_first_text(container, [".rating", ".score", ".star-score"], default="")
            chapter_count_text = _extract_first_text(container, [".chapter-count", ".chapters", ".latest-chapter"], default="")
            chapter_count_match = re.search(r"(\d+)", chapter_count_text)

            novels.append(
                {
                    "title": title,
                    "url": canonical,
                    "genres": genres,
                    "rating": rating or None,
                    "chapter_count": int(chapter_count_match.group(1)) if chapter_count_match else None,
                }
            )
            seen.add(canonical)

        return novels

    def parse_novel_detail(self, html: str, novel_url: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_first_text(soup, ["h1", ".entry-title", ".novel-title"], _extract_meta_content(soup, "og:title"))
        author = _extract_first_text(soup, ['.author a', '.author', '[itemprop="author"]'])
        if not author:
            summary_text = _clean_text(soup.get_text(" ", strip=True))
            author_match = re.search(r"Author\s*:?[ ]+([^|]+?)(?:Genres|Status|Rating|$)", summary_text, re.IGNORECASE)
            if author_match:
                author = _clean_text(author_match.group(1))
        description = _extract_first_text(soup, [".summary__content", ".description", ".entry-content"], _extract_meta_content(soup, "description", "og:description"))
        if description:
            description = _clean_multiline_text(description)

        genres = []
        for genre_anchor in soup.select('a[href*="genre"], .genres a, .summary-content a'):
            genre = _clean_text(genre_anchor.get_text(" ", strip=True))
            href = genre_anchor.get("href") or ""
            if genre and ("genre" in href or genre not in genres):
                if genre not in genres:
                    genres.append(genre)

        cover_url = ""
        cover = soup.select_one('.summary_image img, .post-thumbnail img, .book-cover img, img[alt]')
        if cover and cover.get("src"):
            cover_url = urljoin(novel_url, cover["src"])
        if not cover_url:
            cover_url = _extract_meta_content(soup, "og:image")

        chapter_links = []
        seen = set()
        for anchor in soup.select('a[href*="/chapter-"]'):
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            absolute_url = urljoin(novel_url, href).rstrip("/")
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            chapter_links.append(absolute_url)
        chapter_links.sort(key=_natural_chapter_key)

        return {
            "title": title,
            "author": author,
            "description": description,
            "genres": genres,
            "cover_url": cover_url,
            "source": "noveltrust",
            "chapter_urls": chapter_links,
        }

    def parse_chapter(self, html: str, chapter_url: str) -> Tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        title = _extract_first_text(soup, ["h1", ".chapter-title", ".entry-title"], default="Untitled Chapter")

        content_node = None
        for selector in [
            "#chapter-content",
            ".chapter-content",
            ".entry-content",
            ".text-left",
            "article",
            ".content-area",
        ]:
            content_node = soup.select_one(selector)
            if content_node:
                break

        if content_node is None:
            raise ValueError(f"Chapter content container not found for {chapter_url}")

        for removable in content_node.select("script, style, .ads, .advertisement, .share-links, .nav-links"):
            removable.decompose()

        paragraphs = []
        for paragraph in content_node.select("p"):
            text = _clean_text(paragraph.get_text(" ", strip=True))
            if text:
                paragraphs.append(text)

        if not paragraphs:
            raw_text = _clean_multiline_text(content_node.get_text("\n", strip=True))
            paragraphs = [part for part in raw_text.split("\n\n") if part]

        content = "\n\n".join(paragraphs).strip()
        if len(content) < 50:
            raise ValueError(f"Content too short for {chapter_url}")

        return title, content

    def scrape_list_page(self, page_url: str) -> List[dict]:
        return self.parse_list_page(self.fetch(page_url), page_url)

    def scrape_novel_detail(self, novel_url: str) -> dict:
        return self.parse_novel_detail(self.fetch(novel_url), novel_url)

    def get_novel_name(self, novel_url: str) -> str:
        return novel_url.rstrip("/").split("/")[-1]

    def generate_chapter_urls(self, novel_url: str, start: int, end: int) -> Tuple[List[str], str]:
        if start < 1 or end < start:
            raise ValueError("Invalid chapter range")

        detail = self.scrape_novel_detail(novel_url)
        chapter_urls = detail["chapter_urls"]
        if not chapter_urls:
            raise ValueError("No chapter URLs found on the novel detail page")

        selected = chapter_urls[start - 1:end]
        if not selected:
            raise ValueError("Requested chapter range is outside the available chapters")

        return selected, self.get_novel_name(novel_url)

    def get_total_chapters(self, novel_url: str) -> int:
        detail = self.scrape_novel_detail(novel_url)
        return len(detail["chapter_urls"])

    def scrape_chapter(self, chapter_url: str) -> Tuple[str, str]:
        return self.parse_chapter(self.fetch(chapter_url), chapter_url)

    def scrape_range(self, novel_url: str, start: int, end: int, output_dir: str = "data/output"):
        chapter_urls, novel_name = self.generate_chapter_urls(novel_url, start, end)
        safe_name = re.sub(r'[\\/*?<>:"|]', "", novel_name)
        save_dir = os.path.join(output_dir, safe_name)
        os.makedirs(save_dir, exist_ok=True)

        logger.info("Output directory: %s", save_dir)
        logger.info("Scraping chapters %s to %s", start, end)

        success_count = 0
        fail_count = 0

        for chapter_number, chapter_url in enumerate(chapter_urls, start=start):
            filename = f"Chapter_{chapter_number:04d}.txt"
            filepath = os.path.join(save_dir, filename)
            if os.path.exists(filepath):
                logger.info("Skipping chapter %s because it already exists", chapter_number)
                success_count += 1
                continue

            try:
                title, content = self.scrape_chapter(chapter_url)
                with open(filepath, "w", encoding="utf-8") as handle:
                    handle.write(f"{title}\n")
                    handle.write("=" * 60 + "\n\n")
                    handle.write(content)
                success_count += 1
            except Exception as exc:
                fail_count += 1
                logger.error("Failed to scrape chapter %s: %s", chapter_number, exc)
                error_file = os.path.join(save_dir, f"_error_chapter_{chapter_number}.txt")
                with open(error_file, "w", encoding="utf-8") as handle:
                    handle.write(f"Chapter {chapter_number}\nURL: {chapter_url}\nError: {str(exc)}\n")

        logger.info("Scrape complete. Success: %s | Failed: %s", success_count, fail_count)


def main():
    print("\n" + "=" * 60)
    print("        NOVELTRUST SCRAPER")
    print("=" * 60 + "\n")

    novel_url = input("Novel URL (e.g., https://noveltrust.com/novel/example-title/): ").strip()
    start = int(input("Start chapter: "))
    end = int(input("End chapter: "))

    scraper = NovelScraper(headless=True)
    scraper.scrape_range(novel_url, start, end)


if __name__ == "__main__":
    main()
