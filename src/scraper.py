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
        options.headless = self.headless 
        
        if self.headless:
            options.add_argument("--headless=new")
        
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        print("[INFO] Initializing Chrome WebDriver...")
        return uc.Chrome(options=options)

    def generate_chapter_urls(self, toc_url: str, start: int, end: int) -> Tuple[List[str], str]:
        novel_name = toc_url.rstrip("/").split("/")[-1]
        base_parts = toc_url.split("/s/index/")
        
        if len(base_parts) != 2:
            raise ValueError("Invalid TOC URL format. Expected: https://novelhi.com/s/index/Novel-Name")
        
        base_url = base_parts[0]
        chapter_urls = [f"{base_url}/s/{novel_name}/{num}" for num in range(start, end + 1)]
        
        print(f"[INFO] Generated {len(chapter_urls)} chapter URLs")
        print(f"[DEBUG] Range: {chapter_urls[0]} to {chapter_urls[-1]}")
        
        return chapter_urls, novel_name

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