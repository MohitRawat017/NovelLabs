"""
Scraper API routes - triggers the Python web scraper
"""

import asyncio
import threading
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict

from ..models.schemas import ScrapeRequest, ScrapeStatusResponse

router = APIRouter()

# Store for tracking scrape jobs
scrape_jobs: Dict[str, dict] = {}


def run_scraper_with_detection(job_id: str, toc_url: str, start: int):
    """Run detection + scraping in a background thread"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    
    from scraper import NovelScraper
    
    try:
        scraper = NovelScraper(headless=True)
        driver = scraper.start_driver()
        
        try:
            # Detect total chapters first
            end_chapter = scraper.get_total_chapters(driver, toc_url)
            scrape_jobs[job_id]['total_chapters'] = end_chapter - start + 1
            print(f"[INFO] Detected {end_chapter} chapters, starting scrape from {start}")
        finally:
            driver.quit()
        
        # Now run the actual scraper
        run_scraper(job_id, toc_url, start, end_chapter)
        
    except Exception as e:
        scrape_jobs[job_id]['status'] = 'failed'
        scrape_jobs[job_id]['error'] = f"Detection failed: {str(e)}"
        print(f"[ERROR] Detection failed: {e}")


def run_scraper(job_id: str, toc_url: str, start: int, end: int):
    """Run the scraper in a background thread"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    
    from scraper import NovelScraper
    
    try:
        scrape_jobs[job_id]['status'] = 'running'
        
        scraper = NovelScraper(headless=True)
        
        # Custom scrape with progress updates
        driver = scraper.start_driver()
        
        try:
            chapter_urls, novel_name = scraper.generate_chapter_urls(toc_url, start, end)
            scrape_jobs[job_id]['novel_title'] = novel_name
            scrape_jobs[job_id]['total_chapters'] = len(chapter_urls)
            
            import os
            import re
            novel_name_clean = re.sub(r'[\\/*?<>:"|]', "", novel_name)
            save_dir = Path(__file__).resolve().parent.parent.parent.parent / "data" / "output" / novel_name_clean
            os.makedirs(save_dir, exist_ok=True)
            
            for idx, url in enumerate(chapter_urls, start=start):
                # Check for cancellation
                if scrape_jobs[job_id].get('status') == 'cancelled':
                    print(f"[INFO] Job {job_id} cancelled by user")
                    break
                
                scrape_jobs[job_id]['current_chapter'] = idx - start + 1
                
                filename = f"Chapter_{idx:04d}.txt"
                filepath = save_dir / filename
                
                if filepath.exists():
                    continue
                
                try:
                    title, content = scraper.scrape_chapter(driver, url)
                    
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(f"{title}\n")
                        f.write("=" * 60 + "\n\n")
                        f.write(content)
                
                except Exception as e:
                    print(f"Error scraping chapter {idx}: {e}")
                
                import time
                time.sleep(2)
            
            # Only mark completed if not cancelled
            if scrape_jobs[job_id].get('status') != 'cancelled':
                scrape_jobs[job_id]['status'] = 'completed'
                # Sync to database so novel appears in library
                try:
                    from .novels import sync_novels_to_db
                    sync_novels_to_db()
                    print(f"[INFO] Library synced after scraping {novel_name}")
                except Exception as e:
                    print(f"[WARN] Failed to sync library: {e}")
            
        finally:
            driver.quit()
    
    except Exception as e:
        scrape_jobs[job_id]['status'] = 'failed'
        scrape_jobs[job_id]['error'] = str(e)


@router.post("/start")
async def start_scraping(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """Start a new scraping job"""
    import uuid
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    
    job_id = str(uuid.uuid4())
    
    end_chapter = request.end_chapter
    
    # If auto-detect is needed, set status to detecting and run in background
    if end_chapter is None:
        scrape_jobs[job_id] = {
            'status': 'detecting',
            'current_chapter': 0,
            'total_chapters': 0,
            'novel_title': None,
            'error': None
        }
        
        # Start detection + scraping in background
        thread = threading.Thread(
            target=run_scraper_with_detection,
            args=(job_id, request.toc_url, request.start_chapter)
        )
        thread.start()
        
        return {"job_id": job_id, "message": "Detecting chapters...", "total_chapters": 0}
    
    # If end_chapter provided, start scraping directly
    scrape_jobs[job_id] = {
        'status': 'pending',
        'current_chapter': 0,
        'total_chapters': end_chapter - request.start_chapter + 1,
        'novel_title': None,
        'error': None
    }
    
    # Start scraper in background thread
    thread = threading.Thread(
        target=run_scraper,
        args=(job_id, request.toc_url, request.start_chapter, end_chapter)
    )
    thread.start()
    
    return {"job_id": job_id, "message": "Scraping started", "total_chapters": end_chapter}


@router.get("/status/{job_id}", response_model=ScrapeStatusResponse)
async def get_scrape_status(job_id: str):
    """Get the status of a scraping job"""
    if job_id not in scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = scrape_jobs[job_id]
    return ScrapeStatusResponse(
        status=job['status'],
        current_chapter=job['current_chapter'],
        total_chapters=job['total_chapters'],
        novel_title=job['novel_title'],
        error=job['error']
    )


@router.get("/jobs")
async def list_jobs():
    """List all scraping jobs"""
    return scrape_jobs


@router.post("/cancel/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running scraping job"""
    if job_id not in scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = scrape_jobs[job_id]
    
    if job['status'] in ('completed', 'failed', 'cancelled'):
        return {"message": f"Job already {job['status']}", "status": job['status']}
    
    # Mark as cancelled - the run_scraper loop will check this
    job['status'] = 'cancelled'
    job['error'] = 'Cancelled by user'
    
    return {"message": "Job cancelled", "status": "cancelled"}


@router.delete("/job/{job_id}")
async def remove_job(job_id: str):
    """Remove a completed/failed job from the list"""
    if job_id not in scrape_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del scrape_jobs[job_id]
    return {"message": "Job removed"}

