# 🚀 Prompt for CLI Coding Agent — NovelLabs Production Deployment

## 🎯 Objective

Refactor the existing NovelLabs project from a local-only architecture (SQLite + local files + TTS in backend) into a production-ready system with:

* Read-only deployed backend
* External storage (Cloudflare R2)
* Relational database (PostgreSQL)
* Local-only scraping + TTS pipeline

---

## 🧠 Core Architecture

```
LOCAL (data pipeline):
  scrape + generate audio (TTS)
        ↓
  upload → Cloudflare R2
        ↓
  update → PostgreSQL

PRODUCTION (deployed):
  FastAPI backend (Render)
        ↓
  reads → PostgreSQL + R2
        ↓
  serves → frontend
```

---

## ⚠️ Critical Constraints

1. Production backend MUST NOT:

   * run scraping
   * use FlareSolverr
   * load TTS models

2. Backend must be stateless and read-only

3. All heavy operations happen locally only

---

## 🗄️ Database Design (PostgreSQL)

### Table: novels

```
id (PK)
title
author
cover_url
created_at
```

### Table: chapters

```
id (PK)
novel_id (FK)
chapter_number
title
r2_key TEXT
audio_key TEXT
has_audio BOOLEAN
status TEXT  -- "processing" | "ready"
created_at
```

---

## 📦 Cloud Storage (R2)

### Bucket Structure

```
novels/
  {novel_id}/
    chapters/
      0001.json
      0002.json
    audio/
      0001.mp3
```

### Rules

* Use zero-padded filenames
* Never hardcode paths in backend
* Always store paths in DB (`r2_key`, `audio_key`)

---

## 🔁 Backend Responsibilities (FastAPI)

### MUST implement:

#### 1. Get chapter metadata

* Fetch from PostgreSQL

#### 2. Fetch chapter content from R2

* Using `r2_key`

#### 3. Return response

```
{
  "title": "Chapter 1",
  "content": "...",
  "audio_url": "signed_or_direct_url"
}
```

---

## ⚡ Storage Access Strategy

### Phase 1 (MVP)

* Backend fetches file from R2
* Returns content directly

### Phase 2 (optional)

* Generate signed URLs
* Frontend fetches directly from R2

---

## 🔐 Environment Variables

```
DATABASE_URL=
R2_ACCOUNT_ID=
R2_ACCESS_KEY=
R2_SECRET_KEY=
R2_BUCKET_NAME=
ENABLE_SCRAPING=false
```

---

## 🧪 Local Pipeline Requirements

Implement scripts or endpoints for:

### 1. Scraping

* Uses FlareSolverr (Docker, local only)

### 2. Chapter upload

* Upload JSON to R2
* Save `r2_key` in Postgres

### 3. Audio generation

* Generate audio locally
* Upload to R2
* Update `audio_key`, `has_audio=true`

### 4. Order of operations

```
1. Upload to R2
2. If success → update Postgres
```

---

## 🧱 Code Requirements

* Use FastAPI

* Modular structure:

  * db/
  * storage/
  * api/
  * services/

* Use environment-based config

---

## 🐳 Docker Requirements (Production)

### Backend Dockerfile must:

* NOT include TTS models
* NOT include scraper dependencies
* Be lightweight

---

## 🚀 Deployment Target

Platform: Render

Requirements:

* Deploy FastAPI backend only
* Connect to managed PostgreSQL
* Connect to Cloudflare R2

---

## ❌ Things to Avoid

* Do NOT store chapter content in PostgreSQL
* Do NOT expose raw R2 paths directly
* Do NOT run scraping in production
* Do NOT tightly couple frontend to storage

---

## ✅ Expected Output from CLI Agent

The agent should:

1. Refactor storage layer (SQLite → Postgres + R2)
2. Implement R2 upload + fetch utilities
3. Implement DB models + queries
4. Implement FastAPI endpoints for:

   * listing novels
   * fetching chapters
5. Add environment-based configuration
6. Provide Dockerfile for backend

---

## 🎯 Final Goal

A deployable FastAPI backend that:

* serves novels + chapters + audio
* reads from PostgreSQL + R2
* runs on Render without heavy dependencies

---

Build simple → ensure correctness → then scale.
