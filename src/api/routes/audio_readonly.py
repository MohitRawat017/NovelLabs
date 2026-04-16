"""Read-only audio routes for deployments where TTS generation is disabled."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from ..config import SUPPORTED_TTS_PROVIDERS, TTS_PROVIDER
from ..database import dict_from_row, get_db
from ..storage import build_audio_public_url

router = APIRouter()

_DISABLED_DETAIL = "Audio generation is disabled in this deployment."


def _resolve_provider(provider: Optional[str] = None) -> str:
    resolved = (provider or TTS_PROVIDER).strip().lower()
    if resolved not in SUPPORTED_TTS_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported TTS provider '{resolved}'. Choose one of: kokoro, qwen3, elevenlabs.",
        )
    return resolved


def _resolve_audio_metadata(novel_slug: str, chapter_number: int) -> dict | None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                c.audio_key,
                ca.audio_url,
                ca.status,
                ca.duration,
                ca.progress,
                ca.error,
                ca.provider,
                ca.voice,
                (
                    SELECT COUNT(*)
                    FROM audio_timings at
                    WHERE at.novel_slug = n.slug
                      AND at.chapter_number = c.chapter_number
                ) AS timing_count
            FROM chapters c
            JOIN novels n ON c.novel_id = n.id
            LEFT JOIN chapter_audio ca
                ON ca.novel_slug = n.slug
               AND ca.chapter_number = c.chapter_number
            WHERE n.slug = ? AND c.chapter_number = ?
            """,
            (novel_slug, chapter_number),
        )
        row = dict_from_row(cursor.fetchone())

    if not row:
        return None

    row["resolved_audio_url"] = build_audio_public_url(row.get("audio_key")) or row.get("audio_url")
    row["timing_exists"] = bool(row.get("timing_count"))
    return row


def _readonly_profile_payload(provider: Optional[str] = None) -> dict:
    resolved_provider = _resolve_provider(provider)
    return {
        "exists": False,
        "provider": resolved_provider,
        "supports_voice_cloning": False,
        "read_only": True,
    }


@router.get("/stream/{novel_slug}/{chapter_number}")
async def stream_chapter_audio_readonly(novel_slug: str, chapter_number: int):
    row = _resolve_audio_metadata(novel_slug, chapter_number)
    if not row or not row.get("resolved_audio_url"):
        raise HTTPException(status_code=404, detail="Audio not available")

    return RedirectResponse(url=row["resolved_audio_url"], status_code=307)


@router.get("/status/{novel_slug}/{chapter_number}")
async def check_audio_status_readonly(novel_slug: str, chapter_number: int):
    row = _resolve_audio_metadata(novel_slug, chapter_number)

    if not row:
        return {
            "exists": False,
            "audio_only": False,
            "timing_exists": False,
            "generating": False,
            "status": "not_found",
            "audio_url": None,
            "duration": None,
            "progress": 0,
            "error": None,
            "provider": None,
            "voice": None,
        }

    has_audio = bool(row.get("resolved_audio_url"))
    status = "completed" if has_audio else (row.get("status") or "not_found")

    return {
        "exists": has_audio,
        "audio_only": has_audio,
        "timing_exists": row.get("timing_exists", False),
        "generating": False,
        "status": status,
        "audio_url": row.get("resolved_audio_url"),
        "duration": row.get("duration"),
        "progress": 100 if has_audio else (row.get("progress") or 0),
        "error": row.get("error"),
        "provider": row.get("provider"),
        "voice": row.get("voice"),
    }


@router.get("/timings/{novel_slug}/{chapter_number}")
async def get_chapter_timings_readonly(novel_slug: str, chapter_number: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT chunk_index, start_time, end_time, text
            FROM audio_timings
            WHERE novel_slug = ? AND chapter_number = ?
            ORDER BY chunk_index ASC
            """,
            (novel_slug, chapter_number),
        )
        timings = cursor.fetchall()

    if not timings:
        raise HTTPException(status_code=404, detail="Timing data not found.")

    chunks = [
        {
            "index": row["chunk_index"],
            "text": row["text"],
            "start": row["start_time"],
            "end": row["end_time"],
        }
        for row in timings
    ]
    total_duration = max(chunk["end"] for chunk in chunks)
    return {
        "novel_slug": novel_slug,
        "chapter_number": chapter_number,
        "total_duration": round(total_duration, 3),
        "chunk_count": len(chunks),
        "chunks": chunks,
    }


@router.get("/health")
async def audio_health_readonly(provider: Optional[str] = None):
    return {
        "tts_available": False,
        "provider": _resolve_provider(provider),
        "error": _DISABLED_DETAIL,
        "read_only": True,
    }


@router.get("/voices")
async def audio_voices_readonly(provider: Optional[str] = None):
    _resolve_provider(provider)
    return {}


@router.get("/voices/flat")
async def audio_voices_flat_readonly(provider: Optional[str] = None):
    _resolve_provider(provider)
    return []


@router.get("/profile/{novel_slug}")
async def audio_profile_readonly(novel_slug: str, provider: Optional[str] = None):
    return _readonly_profile_payload(provider)


@router.get("/jobs")
async def audio_jobs_readonly():
    return {"jobs": [], "total": 0}


@router.api_route("/{path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
async def audio_mutation_disabled(path: str):
    raise HTTPException(status_code=503, detail=_DISABLED_DETAIL)
