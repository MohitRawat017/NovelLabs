"""Setup configuration for Novel Scraper package."""

from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="novel-scraper",
    version="1.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A production-grade web scraper for novel chapters",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/novel-scraper",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "beautifulsoup4>=4.12.0",
        "selenium>=4.15.0",
        "undetected-chromedriver>=3.5.0",
    ],
    entry_points={
        "console_scripts": [
            "novel-scraper=src.scraper:main",
        ],
    },
)
