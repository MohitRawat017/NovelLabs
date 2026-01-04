# AudioBook Generator

A complete audiobook production pipeline that scrapes web novels, segments text intelligently, and generates high-quality audio using Kokoro TTS with GPU acceleration.

## Features

- **Web Scraping** - Automated chapter extraction with CloudFlare bypass
- **Smart Segmentation** - Sentence-aware chunking optimized for TTS (250 char max)
- **Multi-language TTS** - 53 voices across 9 languages via Kokoro TTS
- **GPU Acceleration** - CUDA support for faster processing
- **Batch Processing** - Handle single files, chapters, or entire novels
- **Resume Support** - Skip already processed content

## Quick Start

### Prerequisites

- Python 3.8+
- NVIDIA GPU with CUDA (optional, CPU supported)
- Chrome browser

### Installation

1. Clone and setup environment:
```bash
git clone <repository-url>
cd audioBook
python -m venv .venv
.venv\Scripts\activate  # Windows
```

2. Install PyTorch with CUDA:
```bash
# CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# CPU only
pip install torch torchvision torchaudio
```

3. Install dependencies:
```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Project Structure

```
audioBook/
├── src/
│   ├── main.py         # TTS generator (entry point)
│   ├── scraper.py      # Web scraper
│   ├── segmenter.py    # Text segmentation
│   └── config.py       # Configuration
├── data/output/        # Scraped chapters
├── Segmentor/output/   # Segmented JSON files
├── audio/              # Generated audiobooks
└── docs/               # Documentation
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

### Usage

**1. Scrape Novel Chapters**
```bash
python src/scraper.py
```
Enter TOC URL and chapter range when prompted.

**2. Segment Text**
```bash
python src/segmenter.py
```
Processes scraped chapters into TTS-optimized chunks.

**3. Generate Audio**
```bash
python src/main.py
```
Select processing mode and voice, then generate audiobooks.

## Audio Generation Modes

1. **Single File** - Process one JSON segment
2. **Full Novel** - Process all chapters in a folder
3. **Batch** - Process all novels in Segmentor/output
4. **Range** - Process specific chapter range (e.g., 100-200)

## Available Voices

- 🇺🇸 American English (19 voices)
- 🇬🇧 British English (8 voices)
- 🇫🇷 French (1 voice)
- 🇮🇹 Italian (2 voices)
- 🇯🇵 Japanese (5 voices)
- 🇨🇳 Mandarin (8 voices)
- 🇪🇸 Spanish (3 voices)
- 🇮🇳 Hindi (4 voices)
- 🇧🇷 Portuguese (3 voices)

## Configuration

Edit `src/config.py` to customize:
- Output directories
- Browser settings
- Scraper parameters
- Timeout values
- Delay between requests

## Output Format

Generated audio files are saved as:
```
audio/
└── NovelName/
    ├── Chapter_0001.wav
    ├── Chapter_0002.wav
    └── Chapter_0003.wav
```

Each chapter is a single combined audio file with automatic silence between text segments.

## Performance

- **CPU**: ~2-3 seconds per chunk
- **GPU**: ~0.5-1 second per chunk
- **Chapter**: 5-15 minutes (depends on length)

## Troubleshooting

**GPU not detected:**
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

**Chrome driver issues:**
```bash
pip install undetected-chromedriver --upgrade
```

**Scraping blocked:**
- Increase delays in `config.py`
- Use non-headless mode
- Check website terms of service

## Development

### Running Tests
```bash
pytest tests/
```

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

## License

MIT License - See LICENSE file for details.

## Disclaimer

This tool is for personal use only. Users are responsible for complying with website terms of service and copyright laws.

## Future Goals

This project is actively being developed with ambitious expansion plans:

### Audio Models & TTS Enhancement
- **Coqui TTS Support**: Integrate open-source Coqui TTS as a lighter alternative to Kokoro
- **Custom Voice Fine-tuning**: Implement transfer learning to create custom voices from small audio samples
- **Real-time Streaming TTS**: Enable chunk-by-chunk audio streaming for faster user feedback

### Performance & Optimization
- **Multi-GPU Support**: Scale processing across multiple GPUs for batch operations
- **Quantization**: Implement model quantization for deployment on edge devices
- **Caching & CDN Integration**: Cache generated audio and serve via CDN for faster distribution
- **Batch Optimization**: Adaptive batching based on available VRAM

### Features & Functionality
- **Web UI Dashboard**: Build a full-featured web interface for easy audio generation
- **Audio Post-processing**: Add audio enhancement, compression, and normalization
- **Chapter Bookmarking**: Implement bookmarks and progress tracking
- **Audiobook Metadata**: Support for cover art, chapter metadata, and publishing info
- **Format Support**: Add support for MP3, FLAC, and other audio formats
- **Playlist Generation**: Create m3u playlists for seamless chapter playback
