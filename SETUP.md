# AudioBook Generator - Setup Guide

## System Requirements

- Python 3.8 or higher
- 8GB RAM minimum (16GB recommended for GPU)
- NVIDIA GPU with 4GB+ VRAM (optional but recommended)
- 10GB free disk space

## Installation Steps

### 1. Environment Setup

```powershell
# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (Linux/Mac)
source .venv/bin/activate
```

### 2. PyTorch Installation

Check your CUDA version first:
```powershell
nvidia-smi
```

Then install appropriate PyTorch:

**CUDA 12.1:**
```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**CUDA 11.8:**
```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**CPU Only:**
```powershell
pip install torch torchvision torchaudio
```

### 3. Dependencies

```powershell
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 4. Verify Installation

```powershell
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"
```

Expected output:
```
PyTorch: 2.x.x
CUDA: True
```

## Quick Start

### Scrape Novel
```powershell
python src/scraper.py
```
Enter URL: `https://novelhi.com/s/index/Novel-Name`

### Segment Text
```powershell
python src/segmenter.py
```

### Generate Audio
```powershell
python src/main.py
```

## Folder Structure After Setup

```
audioBook/
├── .venv/              # Virtual environment
├── src/                # Source code
├── data/output/        # Scraped chapters
├── Segmentor/output/   # JSON segments
├── audio/              # Generated audiobooks
└── logs/               # Log files
```

## Common Issues

### PyTorch Not Detecting GPU
```powershell
# Reinstall PyTorch
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### Chrome Driver Issues
```powershell
pip install --upgrade undetected-chromedriver
```

### Out of Memory (GPU)
Reduce batch size or use CPU mode.

## Performance Tips

- Use GPU for 3-5x faster processing
- Close other GPU applications
- Process in batches of 50-100 chapters
- Use SSD for faster I/O

## Next Steps

1. Configure settings in `src/config.py`
2. Review voice options (53 available)
3. Start with a small test (1-5 chapters)
4. Scale up to full novels

For detailed documentation, see [README.md](../README.md)
