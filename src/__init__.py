"""
Package initialization for the novel scraper.

NOTE: NovelScraper requires selenium/chromedriver dependencies.
Import it directly from scraper module when needed:
    from scraper import NovelScraper
    
The SCRAPER_AVAILABLE flag can be used to check if deps are installed:
    from scraper import SCRAPER_AVAILABLE
"""

from .scraper import SCRAPER_AVAILABLE

__version__ = "1.0.0"
__all__ = ["SCRAPER_AVAILABLE"]
