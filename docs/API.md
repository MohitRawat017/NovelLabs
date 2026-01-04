# API Documentation

## AudioBookGenerator

Main TTS generator class for processing JSON segments into audio.

### Constructor

```python
AudioBookGenerator(voice="af_heart", output_dir="audio", use_gpu=True)
```

**Parameters:**
- `voice` (str): Voice model ID
- `output_dir` (str): Base output directory
- `use_gpu` (bool): Enable GPU acceleration

### Methods

#### process_chapter()
```python
process_chapter(json_path: str, output_dir: str) -> dict
```
Process single JSON file into audio.

**Returns:** `{'chapter_id': str, 'success': int, 'failed': int}`

#### process_novel()
```python
process_novel(input_path: str, novel_name: Optional[str] = None) -> dict
```
Process all chapters in folder.

**Returns:** `{'novel': str, 'processed': int, 'success': int, 'failed': int}`

#### process_range()
```python
process_range(input_path: str, start: int, end: int, novel_name: Optional[str] = None) -> dict
```
Process specific chapter range.

**Returns:** `{'range': str, 'processed': int, 'success': int, 'failed': int}`

---

## NovelScraper

Web scraper for novel chapters.

### Constructor

```python
NovelScraper(headless: bool = True)
```

### Methods

#### scrape_range()
```python
scrape_range(toc_url: str, start: int, end: int, output_dir: str = "data/output")
```
Scrape chapter range from table of contents.

---

## SmartSegmenter

Text segmentation for TTS optimization.

### Methods

#### process_novel()
```python
process_novel(novel_folder: str, output_base_dir: str = "Segmentor/output") -> dict
```
Segment novel chapters into TTS-optimized chunks.

**Returns:** `{'processed': int, 'total_chunks': int}`
