# NovelLabs – NovelTrust Scraper Plan

## Objective
Build a scalable scraper for **https://noveltrust.com** that extracts:

- Novel metadata
- Chapter list
- Chapter text

and stores them in the NovelLabs data pipeline:

- **PostgreSQL → metadata**
- **Cloudflare R2 → chapter text**

The scraper must be modular so additional novel sites can be supported later.

---

# System Architecture


Frontend (Vercel)
↓
Backend API (Render / FastAPI)
↓
Trigger Scraping Job
↓
Modal Scraper Worker
↓
PostgreSQL (metadata)
Cloudflare R2 (chapter text)


Scraping must **NOT run inside the API server**.  
It runs as an external worker (Modal).

---

# Phase 1 — Analyze Website Structure

The scraper must support three page types.

## 1. Novel List Pages

Examples:


https://noveltrust.com/list/latest-novels/1

https://noveltrust.com/list/latest-novels/2


These pages contain:

- novel title
- novel page link
- genres
- rating
- chapter count

Scraper must extract **all novel links from each list page**.

---

## 2. Novel Detail Page

Example structure:


https://noveltrust.com/novel/
<novel-name>


Contains:

- title
- author
- description
- genres
- cover image
- chapter list

Output:

```json
{
  "title": "Novel Title",
  "author": "Author Name",
  "description": "...",
  "genres": ["Action", "Fantasy"],
  "cover_url": "...",
  "source": "noveltrust"
}
3. Chapter Page

Example structure:

https://noveltrust.com/novel/<novel-name>/chapter-1

Contains:

chapter title

chapter text

Scraper must extract the full clean chapter text.


Phase 3 — HTTP Fetch Layer

Use Cloudscraper to bypass Cloudflare protection.

File: fetcher.py

Responsibilities:

request handling

retry logic

user-agent headers

timeout management

Example:

import cloudscraper

scraper = cloudscraper.create_scraper()

def fetch(url):
    response = scraper.get(url)

    if response.status_code != 200:
        raise Exception("Failed request")

    return response.text