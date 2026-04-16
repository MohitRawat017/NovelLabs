"""Stub scraper routes used when scraping is disabled."""

from fastapi import APIRouter, HTTPException

router = APIRouter()

_DISABLED_DETAIL = "Scraper service is disabled in this deployment."


def _disabled_error() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "scraper_disabled",
            "message": _DISABLED_DETAIL,
        },
    )


@router.get("/jobs")
async def list_jobs_disabled():
    raise _disabled_error()


@router.post("/start")
async def start_scraper_disabled():
    raise _disabled_error()


@router.get("/status/{job_id}")
async def status_scraper_disabled(job_id: str):
    raise _disabled_error()


@router.post("/pause/{job_id}")
async def pause_scraper_disabled(job_id: str):
    raise _disabled_error()


@router.post("/resume/{job_id}")
async def resume_scraper_disabled(job_id: str):
    raise _disabled_error()


@router.post("/cancel/{job_id}")
async def cancel_scraper_disabled(job_id: str):
    raise _disabled_error()
