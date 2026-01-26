import os
import re
import time
from typing import Tuple, List

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class NovelScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless

    def start_driver(self) -> uc.Chrome:
        options = uc.ChromeOptions()
        
        if self.headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        print("[INFO] Initializing Chrome WebDriver...")
        # Use version_main to match Chrome browser version (143)
        return uc.Chrome(options=options, version_main=143)

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

    def get_total_chapters(self, driver: uc.Chrome, toc_url: str) -> int:
        """Scrape the TOC page to find total chapter count"""
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
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(3)  # Extra wait for dynamic content
            
            page_source = driver.page_source
            import re
            
            # Strategy 1: Look for "Content (N)" pattern in headers
            content_match = re.search(r'Content\s*\((\d+)\)', page_source)
            if content_match:
                total = int(content_match.group(1))
                print(f"[INFO] Found {total} chapters from Content header")
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
                    if 10 <= total <= 10000:  # Reasonable chapter count range
                        print(f"[INFO] Found {total} chapters from pattern match")
                        return total
            
            # Strategy 3: Count chapter links on the page
            chapter_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/s/']")
            chapter_texts = []
            for link in chapter_links:
                text = link.text.strip()
                if text.lower().startswith("chapter"):
                    chapter_texts.append(text)
            
            if chapter_texts:
                # Extract the highest chapter number from link texts
                max_chapter = 0
                for text in chapter_texts:
                    match = re.search(r'Chapter\s+(\d+)', text, re.IGNORECASE)
                    if match:
                        num = int(match.group(1))
                        max_chapter = max(max_chapter, num)
                
                if max_chapter > 0:
                    print(f"[INFO] Found {max_chapter} chapters from link texts")
                    return max_chapter
            
            # Strategy 4: Count all chapter list items
            list_items = driver.find_elements(By.CSS_SELECTOR, "li a, .chapter-list a, .chapters a")
            if len(list_items) > 10:  # Reasonable minimum
                total = len(list_items)
                print(f"[INFO] Found {total} chapters from list item count")
                return total
            
            raise ValueError("Could not detect chapter count from page")
            
        except Exception as e:
            print(f"[ERROR] Could not detect chapter count: {e}")
            raise ValueError(f"Could not detect total chapters: {e}")

    def scrape_chapter(self, driver: uc.Chrome, url: str) -> Tuple[str, str]:
        driver.get(url)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "showReading"))
            )
        except:
            raise ValueError("Content container not found - page may not have loaded")

        time.sleep(2)

        title = "Untitled Chapter"
        for tag in ["h1", "h2"]:
            try:
                title_elem = driver.find_element(By.TAG_NAME, tag)
                title = title_elem.text.strip()
                break
            except:
                continue

        try:
            show_reading_div = driver.find_element(By.ID, "showReading")
            paragraphs = show_reading_div.find_elements(By.TAG_NAME, "p")
            
            if paragraphs:
                content = "\n\n".join(p.text.strip() for p in paragraphs if p.text.strip())
            else:
                content = show_reading_div.text.strip()
            
        except Exception as e:
            raise ValueError(f"Could not extract content: {e}")

        if len(content) < 100:
            raise ValueError(f"Content too short ({len(content)} characters)")

        return title, content

    def scrape_range(self, toc_url: str, start: int, end: int, output_dir: str = "data/output"):
        driver = self.start_driver()

        try:
            chapter_urls, novel_name = self.generate_chapter_urls(toc_url, start, end)
            novel_name = re.sub(r'[\\/*?<>:"|]', "", novel_name)

            save_dir = os.path.join(output_dir, novel_name)
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
                    title, content = self.scrape_chapter(driver, url)

                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"{title}\n")
                        f.write("=" * 60 + "\n\n")
                        f.write(content)

                    print(f"✓ {title[:50]}")
                    success_count += 1

                except Exception as e:
                    print(f"✗ {str(e)[:80]}")
                    fail_count += 1
                    
                    error_file = os.path.join(save_dir, f"_error_chapter_{idx}.txt")
                    with open(error_file, "w", encoding="utf-8") as f:
                        f.write(f"Chapter {idx}\nURL: {url}\nError: {str(e)}\n")

                time.sleep(2)

            print("\n" + "=" * 60)
            print(f"[COMPLETE] Success: {success_count} | Failed: {fail_count}")
            print("=" * 60)

        finally:
            driver.quit()


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