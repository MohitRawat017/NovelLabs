"""Unit tests for the novel scraper."""

import unittest
from unittest.mock import Mock, patch
from src.scraper import NovelScraper


class TestNovelScraper(unittest.TestCase):
    """Test cases for NovelScraper class."""

    def setUp(self):
        """Set up test fixtures."""
        self.scraper = NovelScraper(headless=True)

    def test_initialization(self):
        """Test scraper initialization."""
        self.assertTrue(self.scraper.headless)
        
    def test_generate_chapter_urls_valid(self):
        """Test URL generation with valid input."""
        toc_url = "https://novelhi.com/s/index/Test-Novel"
        urls, name = self.scraper.generate_chapter_urls(toc_url, 1, 3)
        
        self.assertEqual(len(urls), 3)
        self.assertEqual(name, "Test-Novel")
        self.assertEqual(urls[0], "https://novelhi.com/s/Test-Novel/1")
        self.assertEqual(urls[-1], "https://novelhi.com/s/Test-Novel/3")

    def test_generate_chapter_urls_invalid(self):
        """Test URL generation with invalid input."""
        with self.assertRaises(ValueError):
            self.scraper.generate_chapter_urls("invalid-url", 1, 3)


if __name__ == "__main__":
    unittest.main()
