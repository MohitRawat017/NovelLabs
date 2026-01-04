# Novel Scraper

A production-grade web scraper for extracting novel chapters from supported websites. Built with Python, Selenium, and undetected-chromedriver for reliable content extraction with anti-detection measures.

## Features

- ✅ **Cloudflare Bypass** - Automated detection avoidance
- ✅ **Resume Support** - Skip already downloaded chapters
- ✅ **Error Handling** - Comprehensive logging and error recovery
- ✅ **Clean Output** - Well-formatted text files with chapter titles
- ✅ **Rate Limiting** - Polite scraping with configurable delays
- ✅ **Production Ready** - Type hints, docstrings, and proper structure

## Project Structure

```
audioBook/
├── src/
│   ├── __init__.py          # Package initialization
│   ├── scraper.py           # Main scraper implementation
│   └── config.py            # Configuration settings
├── data/
│   └── output/              # Downloaded chapters
├── docs/                    # Additional documentation
├── tests/                   # Unit tests
├── logs/                    # Application logs
├── requirements.txt         # Python dependencies
├── .gitignore              # Git ignore rules
└── README.md               # This file
```

## Installation

### Prerequisites

- Python 3.8 or higher
- Chrome browser installed
- Git (optional)

### Setup

1. Clone or download this repository:
```bash
git clone <repository-url>
cd audioBook
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Run the scraper interactively:

```bash
python src/scraper.py
```

You'll be prompted to enter:
- Novel TOC URL (e.g., `https://novelhi.com/s/index/Novel-Name`)
- Start chapter number
- End chapter number

### Programmatic Usage

```python
from src.scraper import NovelScraper

scraper = NovelScraper(headless=True)
scraper.scrape_range(
    toc_url="https://novelhi.com/s/index/Novel-Name",
    start=1,
    end=100
)
```

### Configuration

Modify `src/config.py` to customize:
- Output directories
- Browser settings
- Timeout values
- Delay between requests

## Output Format

Chapters are saved as individual text files:

```
data/output/Novel-Name/
├── Chapter_0001.txt
├── Chapter_0002.txt
└── Chapter_0003.txt
```

Each file contains:
```
Chapter Title
============================================================

Chapter content here...
```

## Supported Websites

Currently supports:
- novelhi.com

Additional sites can be added by extending the scraper class.

## Error Handling

- Failed chapters are logged in `_error_chapter_XXXX.txt` files
- Existing chapters are automatically skipped
- Graceful shutdown ensures browser cleanup

## Best Practices

1. **Be Respectful**: Use reasonable delays between requests
2. **Check Terms**: Ensure scraping is allowed by the website's terms of service
3. **Personal Use**: Only scrape for personal, non-commercial use
4. **Rate Limiting**: Adjust delays in config if you encounter issues

## Troubleshooting

### Chrome driver issues
```bash
# Manually specify Chrome version
pip install undetected-chromedriver --upgrade
```

### Import errors
```bash
# Ensure you're in the correct directory
cd audioBook
python src/scraper.py
```

### Slow performance
- Reduce `delay_between_chapters` in config (not recommended below 1.5s)
- Enable headless mode: `NovelScraper(headless=True)`

## Development

### Running Tests
```bash
pytest tests/
```

### Code Style
This project follows PEP 8 guidelines. Format code with:
```bash
black src/
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](docs/CONTRIBUTING.md) for details.

## License

This project is provided for educational purposes. See [LICENSE](LICENSE) for details.

## Disclaimer

This tool is for personal use only. Users are responsible for complying with website terms of service and copyright laws. The authors assume no liability for misuse.

## Changelog

### Version 1.0.0 (2026-01-04)
- Initial production release
- Support for novelhi.com
- Anti-detection measures implemented
- Resume capability added
- Error logging and recovery

## Support

For issues and feature requests, please open an issue on the repository.

---

**Note**: Always respect website robots.txt and terms of service. Use responsibly.
