"""Legacy scraper API routes guarded behind SCRAPER_ENABLED."""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..config import NOVEL_OUTPUT_DIR, SCRAPER_ENABLED
from ..models.schemas import ScrapeRequest, ScrapeStatusResponse

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_ROOT = NOVEL_OUTPUT_DIR

scrape_jobs: Dict[str, dict] = {}
SCRAPER_DISABLED_DETAIL = {
    "code": "scraper_disabled",
    "message": "Scraper is disabled in this build. Set SCRAPER_ENABLED=true to enable it.",
}

# Import scraper module
try:
    import sys
    sys.path.insert(0, str(BASE_DIR / "src"))
    from scraper import NovelScraper, SCRAPER_AVAILABLE
except ImportError:
    SCRAPER_AVAILABLE = False
    NovelScraper = None


def ensure_scraper_enabled():
    if not SCRAPER_ENABLED:
        raise HTTPException(status_code=503, detail=SCRAPER_DISABLED_DETAIL)


def check_scraper_available():
    ensure_scraper_enabled()
    if not SCRAPER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Scraping service unavailable. Install selenium, beautifulsoup4, and undetected-chromedriver.",
        )


def _safe_folder_name(name: str) -> str:
    return re.sub(r'[\\/*?<>:"|]', "", name).strip()


def _normalize_genres(genres) -> str:
    if not genres:
        return ""
    if isinstance(genres, str):
        return genres
    return ",".join(str(item) for item in genres if item)


def _is_retryable_scrape_error(exc: Exception) -> bool:
    message = str(exc).lower()
    retry_markers = (
        "no such window",
        "target window already closed",
        "web view not found",
        "chrome not reachable",
    )
    return any(marker in message for marker in retry_markers)


def _persist_scraped_output(detail: dict, toc_url: str, folder_name: str, output_dir: Path) -> bool:
    from .chapters import sync_chapters_for_novel
    from .novels import slugify, upsert_novel_record

    chapter_count = len(list(output_dir.glob("Chapter_*.txt")))
    if chapter_count == 0:
        return False

    novel_record = upsert_novel_record(
        slug=slugify(folder_name),
        title=detail["title"] or folder_name,
        description=detail.get("description"),
        genres=_normalize_genres(detail.get("genres")),
        data_path=str(output_dir),
        source_toc_url=detail.get("canonical_url", toc_url),
        cover_url=detail.get("cover_url"),
        chapter_count=chapter_count,
    )
    sync_chapters_for_novel(novel_record["id"], str(output_dir))
    return True


def _run_scraper_job(job_id: str, toc_url: str, start: int, end: int | None):
    scraper = NovelScraper(headless=True)
    job = scrape_jobs[job_id]
    detail = None
    output_dir = None
    folder_name = None

    try:
        job["status"] = "running"

        if end is None or end < start:
            raise ValueError("Invalid chapter range requested")
        effective_end = end

        inferred_name = scraper.get_novel_name(toc_url)
        display_title = re.sub(r"[_-]+", " ", inferred_name).strip().title() or inferred_name
        folder_name = _safe_folder_name(display_title)
        output_dir = OUTPUT_ROOT / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        base_url = toc_url.split('/s/')[0] if '/s/' in toc_url else toc_url.rstrip('/')
        canonical_toc_url = f"{base_url}/s/index/{inferred_name}" if '/s/' in toc_url else toc_url
        detail = {
            "title": display_title,
            "description": None,
            "genres": "",
            "cover_url": None,
            "canonical_url": canonical_toc_url,
        }
        chapter_urls, _ = scraper.generate_chapter_urls(canonical_toc_url, start, effective_end)

        job["novel_title"] = display_title
        job["total_chapters"] = effective_end - start + 1
        job["persisted"] = False

        completed_count = 0
        for chapter_number, chapter_url in enumerate(chapter_urls, start=start):
            if job.get("status") == "cancelled":
                job["error"] = "Cancelled by user"
                return

            target_path = output_dir / f"Chapter_{chapter_number:04d}.txt"
            if target_path.exists():
                completed_count += 1
                job["current_chapter"] = completed_count
                continue

            attempt = 0
            while True:
                try:
                    title, content = scraper.scrape_chapter(chapter_url)
                    break
                except Exception as exc:
                    if attempt >= 1 or not _is_retryable_scrape_error(exc):
                        raise
                    attempt += 1
                    logger.warning(
                        "Retrying chapter %s for %s after transient browser failure: %s",
                        chapter_number,
                        toc_url,
                        exc,
                    )

            with open(target_path, "w", encoding="utf-8") as handle:
                handle.write(f"{title}\n")
                handle.write("=" * 60 + "\n\n")
                handle.write(content)

            completed_count += 1
            job["current_chapter"] = completed_count

        job["persisted"] = _persist_scraped_output(detail, toc_url, folder_name, output_dir)
        job["status"] = "completed"
        job["completed_at"] = datetime.utcnow().isoformat()
    except Exception as exc:
        if detail is not None and output_dir is not None and folder_name is not None:
            try:
                job["persisted"] = _persist_scraped_output(detail, toc_url, folder_name, output_dir)
            except Exception as persist_exc:
                logger.exception("Failed to persist partial scraper output for %s: %s", toc_url, persist_exc)

        job["status"] = "failed"
        job["error"] = str(exc)


run_scraper_job = _run_scraper_job


@router.post("/start")
async def start_scraping(request: ScrapeRequest, background_tasks: BackgroundTasks):
    check_scraper_available()

    try:
        scraper = NovelScraper(headless=True)
        total_chapters = await asyncio.to_thread(scraper.get_total_chapters, request.toc_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to inspect novel before starting scrape: %s", request.toc_url)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to inspect novel URL before starting scrape: {exc}",
        ) from exc

    if total_chapters <= 0:
        raise HTTPException(status_code=400, detail="No chapters were found for this novel URL")

    end_chapter = request.end_chapter or total_chapters

    if end_chapter > total_chapters:
        end_chapter = total_chapters
    if request.start_chapter < 1 or end_chapter < request.start_chapter:
        raise HTTPException(status_code=400, detail="Invalid chapter range")

    job_id = str(uuid.uuid4())
    scrape_jobs[job_id] = {
        "status": "pending",
        "current_chapter": 0,
        "total_chapters": end_chapter - request.start_chapter + 1,
        "novel_title": None,
        "persisted": False,
        "error": None,
    }

    try:
        thread = threading.Thread(
            target=run_scraper_job,
            args=(job_id, request.toc_url, request.start_chapter, end_chapter),
            daemon=True,
        )
        thread.start()
    except Exception as exc:
        scrape_jobs.pop(job_id, None)
        logger.exception("Failed to start scraper job thread for %s", request.toc_url)
        raise HTTPException(status_code=500, detail=f"Failed to start scraper job: {exc}") from exc

    return {
        "job_id": job_id,
        "message": "Scraping started",
        "total_chapters": end_chapter - request.start_chapter + 1,
    }


@router.get("/status/{job_id}", response_model=ScrapeStatusResponse)
async def get_scrape_status(job_id: str):
    ensure_scraper_enabled()
    if job_id not in scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = scrape_jobs[job_id]
    return ScrapeStatusResponse(
        status=job["status"],
        current_chapter=job["current_chapter"],
        total_chapters=job["total_chapters"],
        novel_title=job["novel_title"],
        persisted=job.get("persisted", False),
        error=job.get("error"),
    )


@router.get("/jobs")
async def list_jobs():
    ensure_scraper_enabled()
    return scrape_jobs


@router.post("/cancel/{job_id}")
async def cancel_job(job_id: str):
    ensure_scraper_enabled()
    if job_id not in scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = scrape_jobs[job_id]
    if job["status"] in {"completed", "failed", "cancelled"}:
        return {"message": f"Job already {job['status']}", "status": job["status"]}

    job["status"] = "cancelled"
    job["persisted"] = False
    return {"message": "Job cancelled", "status": "cancelled"}


@router.delete("/job/{job_id}")
async def remove_job(job_id: str):
    ensure_scraper_enabled()
    if job_id not in scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    del scrape_jobs[job_id]
    return {"message": "Job removed"}
