"""Tests for the NovelTrust scraper."""

import os
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import src.scraper as scraper_module
from src.scraper import NovelScraper

LIST_HTML = """
<html>
  <body>
    <article class="novel-card">
      <a href="/novel/shadow-slave/">Shadow Slave</a>
      <div class="genres"><a href="/genre/action">Action</a><a href="/genre/fantasy">Fantasy</a></div>
      <span class="rating">4.9</span>
      <span class="chapters">123 chapters</span>
    </article>
    <article class="novel-card">
      <a href="https://noveltrust.com/novel/lord-of-mysteries/">Lord of Mysteries</a>
      <div class="genres"><a href="/genre/mystery">Mystery</a></div>
      <span class="rating">4.8</span>
      <span class="chapters">1432 chapters</span>
    </article>
  </body>
</html>
"""

DETAIL_HTML = """
<html>
  <head>
    <meta property="og:image" content="https://cdn.example.com/cover.jpg" />
  </head>
  <body>
    <h1>Shadow Slave</h1>
    <div class="author"><a href="/author/guiltythree">Guiltythree</a></div>
    <div class="description">
      A boy in a ruined world.
      He rises through the nightmare.
    </div>
    <div class="genres">
      <a href="/genre/action">Action</a>
      <a href="/genre/fantasy">Fantasy</a>
    </div>
    <div class="chapters">
      <a href="/novel/shadow-slave/chapter-2">Chapter 2</a>
      <a href="/novel/shadow-slave/chapter-1">Chapter 1</a>
      <a href="/novel/shadow-slave/chapter-3">Chapter 3</a>
    </div>
  </body>
</html>
"""

CHAPTER_HTML = """
<html>
  <body>
    <h1>Chapter 1 - Awakening</h1>
    <div class="chapter-content">
      <p>Sunny opened his eyes to a dark and unfamiliar sky.</p>
      <p>A cold wind moved across the ruins as the nightmare began.</p>
      <div class="ads">ignore this</div>
    </div>
  </body>
</html>
"""


@unittest.skipUnless(scraper_module.BeautifulSoup is not None, "beautifulsoup4 is required for scraper tests")
class TestNovelTrustScraper(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(scraper_module, "SCRAPER_AVAILABLE", True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.scraper = NovelScraper(headless=True)

    def test_parse_list_page_extracts_novels(self):
        novels = self.scraper.parse_list_page(LIST_HTML, "https://noveltrust.com/list/latest-novels/1")

        self.assertEqual(len(novels), 2)
        self.assertEqual(novels[0]["title"], "Shadow Slave")
        self.assertEqual(novels[0]["url"], "https://noveltrust.com/novel/shadow-slave")
        self.assertEqual(novels[0]["genres"], ["Action", "Fantasy"])
        self.assertEqual(novels[0]["chapter_count"], 123)

    def test_scrape_novel_detail_extracts_metadata_and_sorted_chapters(self):
        detail = self.scraper.parse_novel_detail(DETAIL_HTML, "https://noveltrust.com/novel/shadow-slave/")

        self.assertEqual(detail["title"], "Shadow Slave")
        self.assertEqual(detail["author"], "Guiltythree")
        self.assertEqual(detail["genres"], ["Action", "Fantasy"])
        self.assertEqual(detail["source"], "noveltrust")
        self.assertEqual(
            detail["chapter_urls"],
            [
                "https://noveltrust.com/novel/shadow-slave/chapter-1",
                "https://noveltrust.com/novel/shadow-slave/chapter-2",
                "https://noveltrust.com/novel/shadow-slave/chapter-3",
            ],
        )

    def test_scrape_chapter_returns_clean_text(self):
        title, content = self.scraper.parse_chapter(
            CHAPTER_HTML,
            "https://noveltrust.com/novel/shadow-slave/chapter-1",
        )

        self.assertEqual(title, "Chapter 1 - Awakening")
        self.assertEqual(
            content,
            "Sunny opened his eyes to a dark and unfamiliar sky.\n\n"
            "A cold wind moved across the ruins as the nightmare began.",
        )

    @patch.object(NovelScraper, "scrape_novel_detail")
    def test_generate_chapter_urls_slices_requested_range(self, mock_detail):
        mock_detail.return_value = {
            "chapter_urls": [
                "https://noveltrust.com/novel/shadow-slave/chapter-1",
                "https://noveltrust.com/novel/shadow-slave/chapter-2",
                "https://noveltrust.com/novel/shadow-slave/chapter-3",
            ]
        }

        chapter_urls, novel_name = self.scraper.generate_chapter_urls(
            "https://noveltrust.com/novel/shadow-slave/",
            2,
            3,
        )

        self.assertEqual(novel_name, "shadow-slave")
        self.assertEqual(
            chapter_urls,
            [
                "https://noveltrust.com/novel/shadow-slave/chapter-2",
                "https://noveltrust.com/novel/shadow-slave/chapter-3",
            ],
        )

    @patch.object(NovelScraper, "generate_chapter_urls")
    @patch.object(NovelScraper, "scrape_chapter")
    def test_scrape_range_writes_expected_file_format(self, mock_scrape_chapter, mock_generate_chapter_urls):
        mock_generate_chapter_urls.return_value = (
            ["https://noveltrust.com/novel/shadow-slave/chapter-1"],
            "shadow-slave",
        )
        mock_scrape_chapter.return_value = (
            "Chapter 1 - Awakening",
            "Sunny opened his eyes to a dark and unfamiliar sky.",
        )

        output_root = Path("tests") / "_scraper_output"
        shutil.rmtree(output_root, ignore_errors=True)
        output_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(output_root, ignore_errors=True))

        self.scraper.scrape_range("https://noveltrust.com/novel/shadow-slave/", 1, 1, output_dir=str(output_root))
        output_path = output_root / "shadow-slave" / "Chapter_0001.txt"
        self.assertTrue(output_path.exists())
        self.assertEqual(
            output_path.read_text(encoding="utf-8"),
            "Chapter 1 - Awakening\n" + "=" * 60 + "\n\nSunny opened his eyes to a dark and unfamiliar sky.",
        )

    @unittest.skipUnless(os.getenv("NOVELTRUST_TEST_NOVEL_URL"), "Set NOVELTRUST_TEST_NOVEL_URL to run the live smoke test")
    def test_live_noveltrust_smoke(self):
        novel_url = os.getenv("NOVELTRUST_TEST_NOVEL_URL")
        detail = self.scraper.scrape_novel_detail(novel_url)

        self.assertTrue(detail["title"])
        self.assertTrue(detail["chapter_urls"])

        chapter_title, chapter_content = self.scraper.scrape_chapter(detail["chapter_urls"][0])
        self.assertTrue(chapter_title)
        self.assertGreater(len(chapter_content), 50)


if __name__ == "__main__":
    unittest.main()
