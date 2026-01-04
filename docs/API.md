# API Documentation

## NovelScraper Class

### Overview
Main scraper class for extracting novel chapters from supported websites.

### Constructor

```python
NovelScraper(headless: bool = True)
```

**Parameters:**
- `headless` (bool): Run browser in headless mode. Default: True

**Example:**
```python
scraper = NovelScraper(headless=False)
```

---

### Methods

#### start_driver()
Initialize Chrome WebDriver with anti-detection configuration.

**Returns:** `uc.Chrome` - Configured WebDriver instance

**Example:**
```python
driver = scraper.start_driver()
```

---

#### generate_chapter_urls()
Generate chapter URLs from table of contents URL.

```python
generate_chapter_urls(toc_url: str, start: int, end: int) -> Tuple[List[str], str]
```

**Parameters:**
- `toc_url` (str): Novel table of contents URL
- `start` (int): Starting chapter number
- `end` (int): Ending chapter number

**Returns:** Tuple of (chapter_urls, novel_name)

**Raises:** `ValueError` if URL format is invalid

**Example:**
```python
urls, name = scraper.generate_chapter_urls(
    "https://novelhi.com/s/index/Novel-Name",
    1,
    100
)
```

---

#### scrape_chapter()
Extract chapter content from a single URL.

```python
scrape_chapter(driver: uc.Chrome, url: str) -> Tuple[str, str]
```

**Parameters:**
- `driver` (uc.Chrome): Active WebDriver instance
- `url` (str): Chapter URL to scrape

**Returns:** Tuple of (title, content)

**Raises:** `ValueError` if content cannot be extracted

**Example:**
```python
title, content = scraper.scrape_chapter(driver, chapter_url)
```

---

#### scrape_range()
Scrape multiple chapters and save to disk.

```python
scrape_range(toc_url: str, start: int, end: int, output_dir: str = "data/output")
```

**Parameters:**
- `toc_url` (str): Novel table of contents URL
- `start` (int): Starting chapter number
- `end` (int): Ending chapter number
- `output_dir` (str): Output directory path. Default: "data/output"

**Example:**
```python
scraper.scrape_range(
    "https://novelhi.com/s/index/Novel-Name",
    1,
    50,
    "custom/output/path"
)
```

---

## Configuration

### Browser Settings (src/config.py)

```python
BROWSER_CONFIG = {
    "window_size": "1920,1080",
    "timeout": 15,
    "delay_between_chapters": 2,
}
```

### Scraper Settings

```python
SCRAPER_CONFIG = {
    "min_content_length": 100,
    "max_retries": 3,
    "headless": False,
}
```

---

## Error Handling

All methods raise appropriate exceptions with descriptive messages:

- `ValueError`: Invalid input or missing content
- `TimeoutError`: Page load timeout
- `Exception`: General errors with detailed messages

Error files are saved to the output directory as `_error_chapter_XXXX.txt`.
