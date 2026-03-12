"""Novel scraper using Selenium and undetected-chromedriver."""

import os
import re
import time
import logging
from pathlib import Path
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)

# Optional dependencies - may not be installed on Render
SCRAPER_AVAILABLE = True
_uc = None
_By = None
_WebDriverWait = None
_EC = None

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    _uc = uc
    _By = By
    _WebDriverWait = WebDriverWait
    _EC = EC
    SCRAPER_AVAILABLE = True
except ImportError:
    pass


def _check_dependencies():
    """Raise error if scraping dependencies are not installed."""
    if not SCRAPER_AVAILABLE:
        raise ImportError(
            "Scraping dependencies not installed. "
            "Install with: pip install selenium beautifulsoup4 undetected-chromedriver"
        )


def _detect_chrome_major_version() -> Optional[int]:
    version = os.getenv("CHROME_VERSION")
    if version:
        try:
            return int(version.split(".")[0])
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid CHROME_VERSION=%s", version)

    if os.name == "nt":
        try:
            import winreg  # type: ignore

            candidates = [
                (winreg.HKEY_CURRENT_USER, r"Software\\Google\\Chrome\\BLBeacon", "version"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\\Google\\Chrome\\BLBeacon", "version"),
                (winreg.HKEY_CURRENT_USER, r"Software\\Chromium\\BLBeacon", "version"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\\Chromium\\BLBeacon", "version"),
            ]
            for hive, subkey, value_name in candidates:
                try:
                    with winreg.OpenKey(hive, subkey) as key:
                        detected = winreg.QueryValueEx(key, value_name)[0]
                        return int(str(detected).split(".")[0])
                except FileNotFoundError:
                    continue
                except OSError:
                    continue
        except Exception as exc:
            logger.debug("Chrome registry detection failed: %s", exc)

    return None


def _quit_driver_safely(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception as exc:
        logger.debug("Ignoring WebDriver shutdown error: %s", exc)


class NovelScraper:
    def __init__(self, headless: bool = True):
        _check_dependencies()  # Raises ImportError if deps not available
        self.headless = headless

    def start_driver(self):
        """Start Chrome WebDriver. Returns undetected_chromedriver.Chrome instance."""
        options = _uc.ChromeOptions()

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        detected_major = _detect_chrome_major_version()
        logger.info("Initializing Chrome WebDriver%s", f" for Chrome {detected_major}" if detected_major else " with auto-detected version")
        if detected_major:
            return _uc.Chrome(options=options, version_main=detected_major)
        return _uc.Chrome(options=options)

    def generate_chapter_urls(self, toc_url: str, start: int, end: int) -> Tuple[List[str], str]:
        # Handle multiple URL formats:
        # - https://novelhi.com/s/index/Novel-Name
        # - https://novelhi.com/s/Novel-Name
        # - https://novelhi.com/s/Novel-Name/123 (chapter URL)
        
        novel_name = toc_url.rstrip("/").split("/")[-1]
        
        # Remove chapter number if present (numeric ending)
        if novel_name.isdigit():
            parts = toc_url.rstrip("/").split("/")
            novel_name = parts[-2] if len(parts) >= 2 else novel_name
        
        # Extract base URL
        if "/s/index/" in toc_url:
            base_url = toc_url.split("/s/index/")[0]
        elif "/s/" in toc_url:
            base_url = toc_url.split("/s/")[0]
        else:
            raise ValueError("Invalid URL format. Expected novelhi.com URL with /s/ path")
        
        chapter_urls = [f"{base_url}/s/{novel_name}/{num}" for num in range(start, end + 1)]
        
        print(f"[INFO] Generated {len(chapter_urls)} chapter URLs")
        print(f"[DEBUG] Range: {chapter_urls[0]} to {chapter_urls[-1]}")
        
        return chapter_urls, novel_name

    def get_novel_name(self, toc_url: str) -> str:
        """Extract novel name from URL"""
        novel_name = toc_url.rstrip("/").split("/")[-1]
        if novel_name.isdigit():
            parts = toc_url.rstrip("/").split("/")
            novel_name = parts[-2] if len(parts) >= 2 else novel_name
        return novel_name

    def get_total_chapters(self, toc_url: str) -> int:
        """Scrape the TOC page to find total chapter count"""
        driver = self.start_driver()
        
        try:
            novel_name = self.get_novel_name(toc_url)
            
            # Build TOC URL - use index page format
            if "/s/index/" in toc_url:
                index_url = toc_url
            elif "/s/" in toc_url:
                base_url = toc_url.split("/s/")[0]
                index_url = f"{base_url}/s/index/{novel_name}"
            else:
                raise ValueError(f"Invalid URL format: {toc_url}")
            
            print(f"[INFO] Fetching chapter count from: {index_url}")
            driver.get(index_url)
            
            try:
                # Wait for page to load
                _WebDriverWait(driver, 20).until(
                    _EC.presence_of_element_located((_By.TAG_NAME, "body"))
                )
                time.sleep(3)  # Extra wait for dynamic content
                
                page_source = driver.page_source
                
                # Strategy 1: Look for "Content (N)" pattern in headers
                content_match = re.search(r'Content\s*\((\d+)\)', page_source)
                if content_match:
                    total = int(content_match.group(1))
                    logger.info(f"Found {total} chapters from Content header")
                    return total
                
                # Strategy 2: Look for chapter count in meta or title
                count_patterns = [
                    r'(\d+)\s*chapters?',
                    r'chapters?\s*[:=]\s*(\d+)',
                    r'total\s*[:=]?\s*(\d+)',
                ]
                for pattern in count_patterns:
                    match = re.search(pattern, page_source, re.IGNORECASE)
                    if match:
                        total = int(match.group(1))
                        logger.info(f"Found {total} chapters from pattern: '{pattern}'")
                        return total
                
                # Strategy 3: Count chapter links (if available)
                chapter_links = driver.find_elements(_By.XPATH, "//a[contains(@href, '/s/') and contains(@href, '/chapter-')]")
                if chapter_links:
                    # Extract chapter numbers and find the maximum
                    chapter_numbers = []
                    for link in chapter_links:
                        match = re.search(r'chapter-(\d+)', link.get_attribute('href'))
                        if match:
                            chapter_numbers.append(int(match.group(1)))
                    
                    if chapter_numbers:
                        total = max(chapter_numbers)
                        logger.info(f"Found {total} chapters by counting links")
                        return total
                
            except Exception as e:
                logger.error(f"Error while trying to determine total chapters: {e}")
            
            # Fallback to the original method if the above strategies fail or are not applicable
            driver.get(toc_url)
            time.sleep(3)  # Wait for page to load
            
            # Method 1: Look for "Content (XXXX)" pattern in h3 tags
            try:
                # Get all h3 elements
                h3_elements = driver.find_elements(_By.CSS_SELECTOR, "h3")
                logger.debug(f"Found {len(h3_elements)} h3 elements")
                
                for h3 in h3_elements:
                    text = h3.text.strip()
                    logger.debug(f"H3 text: '{text}'")
                    # Look for pattern like "Content (2317)"
                    match = re.search(r'Content\s*\((\d+)\)', text, re.IGNORECASE)
                    if match:
                        total = int(match.group(1))
                        logger.info(f"Found {total} total chapters from Content header")
                        return total
            except Exception as e:
                logger.debug(f"Method 1 failed: {e}")
            
            # Method 2: Search page source for "Content (XXX)" pattern
            try:
                page_source = driver.page_source
                match = re.search(r'Content\s*\((\d+)\)', page_source, re.IGNORECASE)
                if match:
                    total = int(match.group(1))
                    logger.info(f"Found {total} total chapters from page source")
                    return total
            except Exception as e:
                logger.debug(f"Method 2 failed: {e}")
            
            # Method 3: Count chapter links in the page
            try:
                # Look for links with "Chapter X" text
                chapter_links = driver.find_elements(_By.XPATH, "//a[contains(text(), 'Chapter')]")
                if chapter_links:
                    # Extract chapter numbers and find the maximum
                    chapter_numbers = []
                    for link in chapter_links:
                        match = re.search(r'Chapter\s+(\d+)', link.text)
                        if match:
                            chapter_numbers.append(int(match.group(1)))
                    
                    if chapter_numbers:
                        total = max(chapter_numbers)
                        logger.info(f"Found {total} total chapters by counting links")
                        return total
            except Exception as e:
                logger.debug(f"Method 3 failed: {e}")
            
            # Method 4: Fallback - use regex on page source to find highest chapter number
            try:
                page_source = driver.page_source
                matches = re.findall(r'Chapter\s+(\d+)', page_source, re.IGNORECASE)
                if matches:
                    numbers = [int(m) for m in matches]
                    total = max(numbers)
                    logger.info(f"Found {total} total chapters from regex fallback")
                    return total
            except Exception as e:
                logger.error(f"All methods failed to detect total chapters: {e}")
            
            raise ValueError("Could not determine total chapter count from TOC page")
        finally:
            _quit_driver_safely(driver)

    def scrape_chapter(self, url: str) -> Tuple[str, str]:
        driver = self.start_driver()

        try:
            driver.get(url)

            try:
                _WebDriverWait(driver, 15).until(
                    _EC.presence_of_element_located((_By.ID, "showReading"))
                )
            except Exception as exc:
                raise ValueError("Content container not found - page may not have loaded") from exc

            time.sleep(2)

            title = "Untitled Chapter"
            for tag in ["h1", "h2"]:
                try:
                    title_elem = driver.find_element(_By.TAG_NAME, tag)
                    title = title_elem.text.strip()
                    break
                except Exception:
                    continue

            try:
                show_reading_div = driver.find_element(_By.ID, "showReading")
                paragraphs = show_reading_div.find_elements(_By.TAG_NAME, "p")

                if paragraphs:
                    content = "\n\n".join(p.text.strip() for p in paragraphs if p.text.strip())
                else:
                    content = show_reading_div.text.strip()

            except Exception as exc:
                raise ValueError(f"Could not extract content: {exc}") from exc

            if len(content) < 100:
                raise ValueError(f"Content too short ({len(content)} characters)")

            return title, content
        finally:
            _quit_driver_safely(driver)

    def scrape_novel_detail(self, toc_url: str) -> dict:
        """Get novel details including title, description, cover, and chapter URLs."""
        driver = self.start_driver()
        
        try:
            novel_name = self.get_novel_name(toc_url)
            
            # Build TOC URL
            if "/s/index/" in toc_url:
                index_url = toc_url
            elif "/s/" in toc_url:
                base_url = toc_url.split("/s/")[0]
                index_url = f"{base_url}/s/index/{novel_name}"
            else:
                index_url = toc_url
            
            driver.get(index_url)
            time.sleep(3)
            page_source = driver.page_source
            
            # Extract novel title
            title = novel_name
            try:
                title_elem = driver.find_element(_By.TAG_NAME, "h1")
                title = title_elem.text.strip()
            except:
                pass
            
            # Extract description
            description = ""
            try:
                desc_elem = driver.find_element(_By.CSS_SELECTOR, ".novel-description, .description, #novelDescription")
                description = desc_elem.text.strip()
            except:
                pass
            
            # Extract cover URL
            cover_url = None
            try:
                cover_elem = driver.find_element(_By.CSS_SELECTOR, ".novel-cover img, .cover img")
                cover_url = cover_elem.get_attribute("src")
            except:
                pass
            
            # Extract genres
            genres = []
            try:
                genre_elems = driver.find_elements(_By.CSS_SELECTOR, ".genres a, .genre a, .novel-genres a")
                genres = [g.text.strip() for g in genre_elems if g.text.strip()]
            except:
                pass
            
            # Extract chapter URLs
            chapter_urls = []
            try:
                # Look for chapter links
                links = driver.find_elements(_By.XPATH, "//a[contains(@href, '/s/')]")
                for link in links:
                    href = link.get_attribute("href")
                    if href and f"/s/{novel_name}/" in href:
                        # Extract chapter number from URL
                        match = re.search(r'/s/[^/]+/(\d+)', href)
                        if match:
                            chapter_urls.append(href)
                
                # Sort by chapter number and deduplicate
                def get_chapter_num(url):
                    match = re.search(r'/s/[^/]+/(\d+)', url)
                    return int(match.group(1)) if match else 0
                
                chapter_urls = sorted(set(chapter_urls), key=get_chapter_num)
            except Exception as e:
                logger.error(f"Failed to extract chapter URLs: {e}")

            if not chapter_urls:
                try:
                    content_match = re.search(r'Content\s*\((\d+)\)', page_source)
                    if content_match:
                        total_chapters = int(content_match.group(1))
                    else:
                        total_chapters = self.get_total_chapters(index_url)
                    chapter_urls, _ = self.generate_chapter_urls(toc_url, 1, total_chapters)
                    logger.info("Fell back to generated chapter URLs for %s", toc_url)
                except Exception as fallback_exc:
                    logger.error("Failed to generate chapter URLs for %s: %s", toc_url, fallback_exc)
            
            return {
                "title": title,
                "description": description,
                "cover_url": cover_url,
                "genres": genres,
                "chapter_urls": chapter_urls,
                "canonical_url": index_url,
            }
        finally:
            _quit_driver_safely(driver)

    def scrape_range(self, toc_url: str, start: int, end: int, output_dir: Optional[str] = None):
        chapter_urls, novel_name = self.generate_chapter_urls(toc_url, start, end)
        novel_name = re.sub(r'[\/*?<>:"|]', "", novel_name)

        output_root = output_dir or os.getenv("NOVEL_OUTPUT_DIR", "data/output")
        save_dir = os.path.join(output_root, novel_name)
        os.makedirs(save_dir, exist_ok=True)

        print(f"[INFO] Output directory: {save_dir}")
        print(f"[INFO] Scraping chapters {start} to {end}\n")

        success_count = 0
        fail_count = 0

        for idx, url in enumerate(chapter_urls, start=start):
            filename = f"Chapter_{idx:04d}.txt"
            filepath = os.path.join(save_dir, filename)

            if os.path.exists(filepath):
                print(f"[SKIP] Chapter {idx} (already exists)")
                success_count += 1
                continue

            print(f"[PROCESSING] Chapter {idx}...", end=" ", flush=True)

            try:
                title, content = self.scrape_chapter(url)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"{title}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(content)

                print(f"? {title[:50]}")
                success_count += 1

            except Exception as e:
                print(f"? {str(e)[:80]}")
                fail_count += 1

                error_file = os.path.join(save_dir, f"_error_chapter_{idx}.txt")
                with open(error_file, "w", encoding="utf-8") as f:
                    f.write(f"Chapter {idx}\nURL: {url}\nError: {str(e)}\n")

            time.sleep(2)

        print("\n" + "=" * 60)
        print(f"[COMPLETE] Success: {success_count} | Failed: {fail_count}")
        print("=" * 60)


def main():
    """Main entry point for the scraper application."""
    print("\n" + "=" * 60)
    print("        NOVEL SCRAPER - PRODUCTION VERSION")
    print("=" * 60 + "\n")

    toc_url = input("Novel TOC URL (e.g., https://novelhi.com/s/index/Novel-Name): ").strip()
    start = int(input("Start chapter: "))
    end = int(input("End chapter: "))

    scraper = NovelScraper(headless=False)
    scraper.scrape_range(toc_url, start, end)


if __name__ == "__main__":
    main()
