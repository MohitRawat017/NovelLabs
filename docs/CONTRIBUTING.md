# Contributing to Novel Scraper

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone <your-fork-url>`
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Test thoroughly
6. Commit with clear messages
7. Push to your fork
8. Open a Pull Request

## Code Standards

### Python Style Guide

- Follow PEP 8
- Use type hints for function parameters and returns
- Write docstrings for all public methods
- Keep functions focused and under 50 lines when possible

### Code Example

```python
def scrape_chapter(self, driver: uc.Chrome, url: str) -> Tuple[str, str]:
    """
    Extract chapter title and content from a single chapter URL.
    
    Args:
        driver: Active Chrome WebDriver instance.
        url: URL of the chapter to scrape.
        
    Returns:
        Tuple containing chapter title and content text.
    """
    # Implementation here
```

## Testing

- Write unit tests for new features
- Ensure all tests pass before submitting PR
- Run tests with: `pytest tests/`

## Commit Messages

Use clear, descriptive commit messages:

```
feat: Add support for new website
fix: Resolve timeout issues in scraper
docs: Update README installation instructions
refactor: Improve error handling in scrape_chapter
```

## Pull Request Process

1. Update README.md with any new features
2. Update version number if applicable
3. Describe changes clearly in PR description
4. Link any related issues
5. Wait for review and address feedback

## Reporting Issues

When reporting bugs, include:
- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

## Feature Requests

For new features:
- Describe the use case
- Explain the benefit
- Provide examples if applicable

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Maintain professionalism

Thank you for contributing!
