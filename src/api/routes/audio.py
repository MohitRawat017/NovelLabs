"""
Audio API routes for the local TTS stack.
"""

from __future__ import annotations

import json
import io
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..config import (
    AUDIO_DIR,
    QWEN_TTS_API_STYLE,
    QWEN_TTS_LANGUAGE,
    TTS_PROVIDER,
    TTS_VOICE_PROFILE_DIR,
)
from ..database import dict_from_row, get_db
from ..services.tts_provider import ENGLISH_VOICES, get_tts_provider

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
AUDIO_ROOT = Path(AUDIO_DIR)
AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
VOICE_PROFILE_ROOT = Path(TTS_VOICE_PROFILE_DIR)
VOICE_PROFILE_ROOT.mkdir(parents=True, exist_ok=True)
tts_jobs: dict = {}


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _round_seconds(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(max(0.0, value), 2)


def _build_job_status(job: Optional[dict]) -> dict:
    if not job:
        return {}

    started_monotonic = job.get("started_monotonic")
    elapsed_seconds: Optional[float] = None
    if isinstance(started_monotonic, (int, float)):
        elapsed_seconds = time.monotonic() - float(started_monotonic)

    total_chunks = job.get("total_chunks")
    completed_chunks = int(job.get("completed_chunks") or 0)
    current_chunk = job.get("current_chunk")

    average_chunk_seconds: Optional[float] = None
    if elapsed_seconds is not None and completed_chunks > 0:
        average_chunk_seconds = elapsed_seconds / completed_chunks

    current_chunk_started_monotonic = job.get("current_chunk_started_monotonic")
    current_chunk_elapsed_seconds: Optional[float] = None
    if isinstance(current_chunk_started_monotonic, (int, float)):
        current_chunk_elapsed_seconds = time.monotonic() - float(current_chunk_started_monotonic)

    estimated_remaining_seconds: Optional[float] = None
    if (
        total_chunks is not None
        and isinstance(total_chunks, int)
        and total_chunks >= completed_chunks
        and average_chunk_seconds is not None
        and job.get("status") == "generating"
    ):
        estimated_remaining_seconds = average_chunk_seconds * max(total_chunks - completed_chunks, 0)
    elif job.get("status") == "completed":
        estimated_remaining_seconds = 0.0

    live_progress = job.get("progress")
    if (
        job.get("status") == "generating"
        and isinstance(total_chunks, int)
        and total_chunks > 0
        and current_chunk_elapsed_seconds is not None
    ):
        chunk_span = 90 / total_chunks
        progress_floor = (completed_chunks / total_chunks) * 90
        expected_chunk_seconds = average_chunk_seconds or job.get("last_chunk_seconds") or 15.0
        if expected_chunk_seconds and expected_chunk_seconds > 0:
            chunk_fraction = min(current_chunk_elapsed_seconds / expected_chunk_seconds, 0.95)
            live_progress = round(progress_floor + (chunk_span * chunk_fraction), 2)
        else:
            live_progress = round(progress_floor, 2)
    elif job.get("status") == "completed":
        live_progress = 100.0

    return {
        "job_status": job.get("status"),
        "message": job.get("message"),
        "progress": live_progress,
        "current_chunk": current_chunk,
        "completed_chunks": completed_chunks,
        "total_chunks": total_chunks,
        "elapsed_seconds": _round_seconds(elapsed_seconds),
        "average_chunk_seconds": _round_seconds(average_chunk_seconds),
        "current_chunk_elapsed_seconds": _round_seconds(current_chunk_elapsed_seconds),
        "estimated_remaining_seconds": _round_seconds(estimated_remaining_seconds),
        "started_at": job.get("started_at"),
        "updated_at": job.get("updated_at"),
    }


def _get_audio_paths(novel_slug: str, chapter_number: int) -> tuple[Path, Path]:
    audio_dir = AUDIO_ROOT / novel_slug
    audio_dir.mkdir(parents=True, exist_ok=True)
    return (
        audio_dir / f"Chapter_{chapter_number:04d}.wav",
        audio_dir / f"Chapter_{chapter_number:04d}_timing.json",
    )


def _relative_audio_url(novel_slug: str, chapter_number: int) -> str:
    return f"/audio/{novel_slug}/Chapter_{chapter_number:04d}.wav"


def _audio_job_key(novel_slug: str, chapter_number: int) -> str:
    return f"{novel_slug}_{chapter_number}"


def _voice_profile_public(profile: Optional[dict]) -> dict:
    if not profile:
        return {
            "exists": False,
            "provider": TTS_PROVIDER,
        }
    return {
        "exists": True,
        "id": profile["id"],
        "provider": profile["provider"],
        "voice_name": profile.get("voice_name"),
        "display_name": profile.get("display_name"),
        "ref_text": profile.get("ref_text"),
        "language": profile.get("language"),
        "has_reference_audio": bool(profile.get("ref_audio_path")),
        "updated_at": profile.get("updated_at"),
    }


def _get_novel_record(novel_slug: str) -> Optional[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM novels WHERE slug = ?", (novel_slug,))
        return dict_from_row(cursor.fetchone())


def _get_novel_tts_profile(novel_slug: str, provider_name: str = TTS_PROVIDER) -> Optional[dict]:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.*
            FROM novel_tts_profiles p
            JOIN novels n ON p.novel_id = n.id
            WHERE n.slug = ? AND p.provider = ?
            """,
            (novel_slug, provider_name),
        )
        return dict_from_row(cursor.fetchone())


def _upsert_novel_tts_profile(
    *,
    novel_id: int,
    provider_name: str,
    voice_name: Optional[str],
    display_name: Optional[str],
    ref_audio_path: Optional[str],
    ref_text: Optional[str],
    language: Optional[str],
) -> dict:
    now = datetime.utcnow()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM novel_tts_profiles
            WHERE novel_id = ? AND provider = ?
            """,
            (novel_id, provider_name),
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """
                UPDATE novel_tts_profiles
                SET voice_name = ?, display_name = ?, ref_audio_path = ?, ref_text = ?, language = ?, updated_at = ?
                WHERE novel_id = ? AND provider = ?
                """,
                (voice_name, display_name, ref_audio_path, ref_text, language, now, novel_id, provider_name),
            )
        else:
            cursor.execute(
                """
                INSERT INTO novel_tts_profiles
                    (novel_id, provider, voice_name, display_name, ref_audio_path, ref_text, language, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (novel_id, provider_name, voice_name, display_name, ref_audio_path, ref_text, language, now),
            )

        cursor.execute(
            "SELECT * FROM novel_tts_profiles WHERE novel_id = ? AND provider = ?",
            (novel_id, provider_name),
        )
        row = cursor.fetchone()
    return dict_from_row(row)


def _delete_novel_tts_profile(novel_slug: str, provider_name: str = TTS_PROVIDER) -> Optional[dict]:
    profile = _get_novel_tts_profile(novel_slug, provider_name)
    if not profile:
        return None

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novel_tts_profiles WHERE id = ?", (profile["id"],))

    ref_audio_path = profile.get("ref_audio_path")
    if ref_audio_path:
        try:
            Path(ref_audio_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to remove saved voice profile audio: %s", ref_audio_path, exc_info=True)
    return profile


def _save_reference_audio(novel_slug: str, source_filename: str, content: bytes) -> Path:
    extension = Path(source_filename).suffix.lower() or ".wav"
    if extension not in {".wav", ".mp3", ".flac", ".m4a", ".ogg"}:
        raise HTTPException(status_code=400, detail="Unsupported reference audio format")

    target_dir = VOICE_PROFILE_ROOT / novel_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{TTS_PROVIDER}_reference{extension}"
    target_path.write_bytes(content)
    return target_path


def _validate_reference_audio_for_provider(content: bytes, source_filename: str) -> None:
    extension = Path(source_filename).suffix.lower() or ".wav"
    if TTS_PROVIDER == "qwen3" and QWEN_TTS_API_STYLE == "demo" and extension != ".wav":
        raise HTTPException(
            status_code=400,
            detail="Qwen local demo mode currently expects a WAV reference clip. Convert your voice sample to .wav and upload it again.",
        )

    try:
        sf.read(io.BytesIO(content), dtype="float32", always_2d=False)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Reference audio could not be decoded. Use a clean WAV clip "
                "(PCM WAV, mono preferred, around 5-15 seconds). "
                f"Original error: {exc}"
            ),
        ) from exc


def _require_provider():
    try:
        return get_tts_provider()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _load_chapter_content(novel_slug: str, chapter_number: int) -> tuple[int, str]:
    import httpx

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.id, c.content, c.content_path, c.content_url
            FROM chapters c
            JOIN novels n ON c.novel_id = n.id
            WHERE n.slug = ? AND c.chapter_number = ?
            """,
            (novel_slug, chapter_number),
        )
        chapter = cursor.fetchone()

    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found in database")

    content = chapter["content"]
    if not content and chapter["content_path"]:
        chapter_file = Path(chapter["content_path"])
        if chapter_file.exists():
            raw = chapter_file.read_text(encoding="utf-8")
            lines = raw.splitlines()
            content = "\n".join(lines[3:] if len(lines) > 3 else lines).strip()

    if not content and chapter["content_url"]:
        try:
            response = httpx.get(chapter["content_url"], timeout=15)
            if response.status_code == 200:
                content = response.text.strip()
        except Exception as exc:
            logger.warning("Failed to fetch chapter content from %s: %s", chapter["content_url"], exc)

    if not content:
        raise HTTPException(status_code=400, detail="Chapter content is empty")

    return chapter["id"], content


def _write_timings_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_audio_metadata(
    novel_slug: str,
    chapter_number: int,
    voice: str,
    status: str,
    *,
    provider_name: str = TTS_PROVIDER,
    audio_url: Optional[str] = None,
    duration: Optional[float] = None,
    progress: float = 0.0,
    error: Optional[str] = None,
) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chapter_audio (novel_slug, chapter_number, provider, voice, status, audio_url, duration, error, progress, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (novel_slug, chapter_number)
            DO UPDATE SET
                provider = excluded.provider,
                voice = excluded.voice,
                status = excluded.status,
                audio_url = excluded.audio_url,
                duration = excluded.duration,
                error = excluded.error,
                progress = excluded.progress,
                updated_at = excluded.updated_at
            """,
            (
                novel_slug,
                chapter_number,
                provider_name,
                voice,
                status,
                audio_url,
                duration,
                error,
                progress,
                datetime.utcnow(),
                datetime.utcnow(),
            ),
        )


def _replace_timings(novel_slug: str, chapter_number: int, chunks: list[dict]) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM audio_timings WHERE novel_slug = ? AND chapter_number = ?",
            (novel_slug, chapter_number),
        )
        for chunk in chunks:
            cursor.execute(
                """
                INSERT INTO audio_timings (novel_slug, chapter_number, chunk_index, start_time, end_time, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    novel_slug,
                    chapter_number,
                    chunk["index"],
                    chunk["start"],
                    chunk["end"],
                    chunk["text"],
                    datetime.utcnow(),
                ),
            )


def _mark_chapter_audio_path(novel_slug: str, chapter_number: int, audio_path: Path) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE chapters
            SET audio_path = ?
            WHERE id = (
                SELECT c.id
                FROM chapters c
                JOIN novels n ON c.novel_id = n.id
                WHERE n.slug = ? AND c.chapter_number = ?
            )
            """,
            (str(audio_path), novel_slug, chapter_number),
        )


def _parse_audio_job_key(job_key: str) -> Optional[tuple[str, int]]:
    match = re.match(r"^(?P<novel_slug>.+)_(?P<chapter_number>\d+)$", job_key)
    if not match:
        return None
    return match.group("novel_slug"), int(match.group("chapter_number"))


def _serialize_audio_job(row: Optional[dict], live_job: Optional[dict] = None) -> Optional[dict]:
    if not row:
        return None

    novel_slug = row["novel_slug"]
    chapter_number = row["chapter_number"]
    audio_path, _ = _get_audio_paths(novel_slug, chapter_number)
    audio_exists = audio_path.exists()
    job_status = _build_job_status(live_job)
    inferred_status = "completed" if audio_exists else (job_status.get("job_status") or row.get("status") or "pending")
    inferred_progress = (
        100.0
        if audio_exists
        else float(job_status.get("progress", row.get("progress") or 0.0))
    )

    return {
        "job_id": f"audio:{novel_slug}:{chapter_number}",
        "job_key": _audio_job_key(novel_slug, chapter_number),
        "novel_slug": novel_slug,
        "novel_title": row.get("novel_title"),
        "chapter_number": chapter_number,
        "chapter_title": row.get("chapter_title") or f"Chapter {chapter_number}",
        "status": inferred_status,
        "progress": round(max(inferred_progress, 0.0), 2),
        "provider": row.get("provider") or (TTS_PROVIDER if inferred_status != "not_found" else None),
        "voice": row.get("voice"),
        "audio_url": row.get("audio_url") or (_relative_audio_url(novel_slug, chapter_number) if audio_exists else None),
        "duration": row.get("duration") or live_job.get("duration") if live_job else row.get("duration"),
        "error": row.get("error") or (live_job.get("error") if live_job else None),
        "exists": audio_exists,
        "current_chunk": job_status.get("current_chunk"),
        "completed_chunks": job_status.get("completed_chunks", 0),
        "total_chunks": job_status.get("total_chunks"),
        "elapsed_seconds": job_status.get("elapsed_seconds"),
        "average_chunk_seconds": job_status.get("average_chunk_seconds"),
        "estimated_remaining_seconds": job_status.get("estimated_remaining_seconds"),
        "message": job_status.get("message") or row.get("status"),
        "updated_at": job_status.get("updated_at") or row.get("updated_at") or row.get("created_at"),
        "started_at": job_status.get("started_at") or row.get("created_at"),
    }


def _sortable_timestamp(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


@router.get("/wake")
async def wake_tts_service():
    provider = _require_provider()
    return {"status": "ready", **provider.health()}


@router.get("/health")
async def tts_health_check():
    try:
        provider = get_tts_provider()
    except Exception as exc:
        return {
            "tts_available": False,
            "provider": TTS_PROVIDER,
            "error": str(exc),
        }

    health = provider.health()
    return {
        "tts_available": True,
        "provider": health["provider"],
        "model_loaded": True,
        "gpu_enabled": health["device"] == "cuda",
        "device": health["device"],
        "gpu_name": health["gpu_name"],
        "supports_voice_cloning": health.get("supports_voice_cloning", False),
        "service_style": health.get("service_style"),
        "base_url": health.get("base_url"),
    }


@router.get("/voices")
async def list_voices():
    try:
        return get_tts_provider().list_voices()
    except Exception:
        return ENGLISH_VOICES


@router.get("/voices/flat")
async def list_voices_flat():
    provider = get_tts_provider()
    voices = []
    for group, group_voices in provider.list_voices().items():
        for voice in group_voices:
            voices.append({"id": voice, "group": group})
    return voices


@router.get("/stream/{novel_slug}/{chapter_number}")
async def stream_chapter_audio(novel_slug: str, chapter_number: int):
    audio_path, _ = _get_audio_paths(novel_slug, chapter_number)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio not generated yet. Use /generate first.")

    return FileResponse(
        audio_path,
        media_type="audio/wav",
        filename=f"{novel_slug}_chapter_{chapter_number}.wav",
    )


@router.get("/status/{novel_slug}/{chapter_number}")
async def check_audio_status(novel_slug: str, chapter_number: int):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, audio_url, duration, progress, error
                 , provider, voice
            FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
            """,
            (novel_slug, chapter_number),
        )
        row = cursor.fetchone()

    audio_path, timing_path = _get_audio_paths(novel_slug, chapter_number)
    job = tts_jobs.get(_audio_job_key(novel_slug, chapter_number), {})
    audio_exists = audio_path.exists()
    timing_exists = timing_path.exists()
    job_status = _build_job_status(job)

    if row:
        inferred_audio_url = row["audio_url"] or (_relative_audio_url(novel_slug, chapter_number) if audio_exists else None)
        inferred_status = "completed" if audio_exists else (job_status.get("job_status") or row["status"])
        live_progress = (
            100
            if audio_exists
            else job_status.get("progress", row["progress"] or 0)
        )
        return {
            "exists": audio_exists,
            "audio_only": audio_exists,
            "timing_exists": timing_exists,
            "generating": inferred_status == "generating" and not audio_exists,
            "status": inferred_status,
            "audio_url": inferred_audio_url,
            "duration": row["duration"],
            "progress": live_progress,
            "error": row["error"],
            "provider": row["provider"],
            "voice": row["voice"],
            **job_status,
        }

    return {
        "exists": audio_exists,
        "audio_only": audio_exists,
        "timing_exists": timing_exists,
        "generating": job.get("status") == "generating" and not audio_exists,
        "status": "completed" if audio_exists else ("generating" if job.get("status") == "generating" else "not_found"),
        "audio_url": _relative_audio_url(novel_slug, chapter_number) if audio_exists else None,
        "duration": job.get("duration"),
        "progress": 100 if audio_exists else job_status.get("progress", job.get("progress", 0)),
        "error": job.get("error"),
        **job_status,
    }


@router.get("/jobs")
async def list_audio_jobs(novel_slug: Optional[str] = None):
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT
                ca.*,
                n.title AS novel_title,
                c.title AS chapter_title
            FROM chapter_audio ca
            LEFT JOIN novels n ON n.slug = ca.novel_slug
            LEFT JOIN chapters c
                ON c.novel_id = n.id
               AND c.chapter_number = ca.chapter_number
        """
        params: list = []
        if novel_slug:
            query += " WHERE ca.novel_slug = ?"
            params.append(novel_slug)
        query += " ORDER BY COALESCE(ca.updated_at, ca.created_at) DESC, ca.chapter_number DESC"
        cursor.execute(query, params)
        rows = [dict_from_row(row) for row in cursor.fetchall()]

    rows_by_key = {
        _audio_job_key(row["novel_slug"], row["chapter_number"]): row
        for row in rows
        if row is not None
    }

    for job_key in list(tts_jobs.keys()):
        parsed = _parse_audio_job_key(job_key)
        if not parsed:
            continue
        live_novel_slug, live_chapter_number = parsed
        if novel_slug and live_novel_slug != novel_slug:
            continue
        if job_key not in rows_by_key:
            rows_by_key[job_key] = {
                "novel_slug": live_novel_slug,
                "chapter_number": live_chapter_number,
                "provider": TTS_PROVIDER,
                "voice": None,
                "status": tts_jobs[job_key].get("status"),
                "audio_url": None,
                "duration": tts_jobs[job_key].get("duration"),
                "error": tts_jobs[job_key].get("error"),
                "progress": tts_jobs[job_key].get("progress", 0.0),
                "chapter_title": f"Chapter {live_chapter_number}",
                "novel_title": None,
                "created_at": None,
                "updated_at": tts_jobs[job_key].get("updated_at"),
            }

    jobs = [
        _serialize_audio_job(row, tts_jobs.get(job_key))
        for job_key, row in rows_by_key.items()
    ]
    jobs = [job for job in jobs if job is not None]
    jobs.sort(
        key=lambda job: (
            _sortable_timestamp(job.get("updated_at")),
            job.get("chapter_number") or 0,
        ),
        reverse=True,
    )
    return {"jobs": jobs, "total": len(jobs)}


@router.get("/timings/{novel_slug}/{chapter_number}")
async def get_chapter_timings(novel_slug: str, chapter_number: int):
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

    if timings:
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

    _, timing_path = _get_audio_paths(novel_slug, chapter_number)
    if timing_path.exists():
        return json.loads(timing_path.read_text(encoding="utf-8"))

    raise HTTPException(status_code=404, detail="Timing data not found. Generate audio first.")


@router.get("/profile/{novel_slug}")
async def get_novel_voice_profile(novel_slug: str):
    provider = _require_provider()
    profile = _get_novel_tts_profile(novel_slug)
    payload = _voice_profile_public(profile)
    payload["supports_voice_cloning"] = getattr(provider, "supports_voice_cloning", False)
    payload["provider"] = provider.health().get("provider", TTS_PROVIDER)
    return payload


@router.post("/profile/{novel_slug}")
async def upload_novel_voice_profile(
    novel_slug: str,
    audio: UploadFile = File(...),
    ref_text: str = Form(""),
    display_name: str = Form(""),
    voice_name: str = Form("novel-default"),
    language: str = Form(QWEN_TTS_LANGUAGE),
    auto_transcribe: bool = Form(True),
):
    provider = _require_provider()
    if not getattr(provider, "supports_voice_cloning", False):
        raise HTTPException(status_code=400, detail=f"{TTS_PROVIDER} does not support saved voice profiles")

    novel = _get_novel_record(novel_slug)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")

    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Reference audio file is empty")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Reference audio must be 25MB or smaller")
    _validate_reference_audio_for_provider(content, audio.filename or "reference.wav")

    target_path = _save_reference_audio(novel_slug, audio.filename or "reference.wav", content)
    transcription = ref_text.strip()
    if not transcription and auto_transcribe:
        try:
            transcription = (provider.transcribe_reference_audio(content, audio.filename or target_path.name) or "").strip()
        except Exception as exc:
            logger.warning("Reference transcription failed for %s: %s", novel_slug, exc)

    profile = _upsert_novel_tts_profile(
        novel_id=novel["id"],
        provider_name=TTS_PROVIDER,
        voice_name=(voice_name or "novel-default").strip(),
        display_name=(display_name or audio.filename or "Novel Voice").strip(),
        ref_audio_path=str(target_path),
        ref_text=transcription or None,
        language=(language or QWEN_TTS_LANGUAGE).strip(),
    )
    payload = _voice_profile_public(profile)
    payload["supports_voice_cloning"] = True
    return payload


@router.delete("/profile/{novel_slug}")
async def delete_novel_voice_profile(novel_slug: str):
    provider = _require_provider()
    if not getattr(provider, "supports_voice_cloning", False):
        raise HTTPException(status_code=400, detail=f"{TTS_PROVIDER} does not support saved voice profiles")

    deleted = _delete_novel_tts_profile(novel_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="No saved voice profile for this novel")
    return {"status": "deleted", "provider": TTS_PROVIDER}


@router.post("/generate/{novel_slug}/{chapter_number}")
async def generate_chapter_audio(
    novel_slug: str,
    chapter_number: int,
    voice: str = "af_heart",
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    provider = _require_provider()
    profile = _get_novel_tts_profile(novel_slug)
    if getattr(provider, "supports_voice_cloning", False) and not profile:
        raise HTTPException(
            status_code=400,
            detail="No saved Qwen voice profile for this novel. Upload one from the novel page first.",
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, audio_url, duration
            FROM chapter_audio
            WHERE novel_slug = ? AND chapter_number = ?
            """,
            (novel_slug, chapter_number),
        )
        existing = cursor.fetchone()

    if existing:
        if existing["status"] == "completed":
            return {
                "status": "exists",
                "message": "Audio already generated",
                "audio_url": existing["audio_url"],
                "duration": existing["duration"],
            }
        if existing["status"] == "generating":
            return {"status": "already_generating", "message": "Audio generation in progress"}

    _, content = _load_chapter_content(novel_slug, chapter_number)
    _save_audio_metadata(
        novel_slug,
        chapter_number,
        voice,
        "generating",
        provider_name=provider.health().get("provider", TTS_PROVIDER),
        progress=0.0,
        error=None,
    )

    job_key = _audio_job_key(novel_slug, chapter_number)
    now_iso = _utc_now_iso()
    tts_jobs[job_key] = {
        "status": "generating",
        "progress": 0,
        "message": "Queued for generation",
        "current_chunk": 0,
        "completed_chunks": 0,
        "total_chunks": None,
        "current_chunk_started_monotonic": None,
        "last_chunk_seconds": None,
        "started_at": now_iso,
        "updated_at": now_iso,
        "started_monotonic": time.monotonic(),
    }
    background_tasks.add_task(run_tts_generation, novel_slug, chapter_number, content, voice, job_key)

    return {
        "status": "queued",
        "message": f"Audio generation started for {novel_slug} chapter {chapter_number}",
        "voice": voice,
    }


def run_tts_generation(novel_slug: str, chapter_number: int, text: str, voice: str, job_key: str):
    import soundfile as sf

    provider = get_tts_provider()
    audio_path, timing_path = _get_audio_paths(novel_slug, chapter_number)
    profile = _get_novel_tts_profile(novel_slug)
    provider_name = provider.health().get("provider", TTS_PROVIDER)

    try:
        chunks = split_text_into_chunks(text, max_length=500)
        if not chunks:
            raise ValueError("No chunks to process")

        existing_job = tts_jobs.get(job_key, {})
        tts_jobs[job_key] = {
            "status": "generating",
            "progress": 0,
            "message": "Preparing audio chunks",
            "current_chunk": 0,
            "completed_chunks": 0,
            "total_chunks": len(chunks),
            "current_chunk_started_monotonic": None,
            "last_chunk_seconds": existing_job.get("last_chunk_seconds"),
            "started_at": existing_job.get("started_at") or _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "started_monotonic": existing_job.get("started_monotonic") or time.monotonic(),
        }

        audio_segments = []
        chunk_timings = []
        current_time = 0.0
        silence_duration = 0.3
        silence = np.zeros(int(provider.sample_rate * silence_duration), dtype=np.float32)

        for idx, chunk in enumerate(chunks):
            progress = round((idx / len(chunks)) * 90, 2)
            chunk_started_monotonic = time.monotonic()
            tts_jobs[job_key].update(
                {
                    "status": "generating",
                    "progress": progress,
                    "message": f"Synthesizing chunk {idx + 1} of {len(chunks)}",
                    "current_chunk": idx + 1,
                    "completed_chunks": idx,
                    "total_chunks": len(chunks),
                    "current_chunk_started_monotonic": chunk_started_monotonic,
                    "updated_at": _utc_now_iso(),
                }
            )
            logger.info(
                "TTS progress %s chapter %s: starting chunk %s/%s (%.2f%%)",
                novel_slug,
                chapter_number,
                idx + 1,
                len(chunks),
                progress,
            )
            _save_audio_metadata(
                novel_slug,
                chapter_number,
                voice,
                "generating",
                provider_name=provider_name,
                progress=progress,
            )

            audio = provider.synthesize(chunk.strip(), voice, profile=profile)
            if audio.ndim > 1:
                audio = audio.squeeze()
            audio = np.asarray(audio, dtype=np.float32)
            duration = len(audio) / provider.sample_rate
            completed_chunks = idx + 1
            chunk_elapsed_seconds = time.monotonic() - chunk_started_monotonic
            completed_progress = round((completed_chunks / len(chunks)) * 90, 2)

            tts_jobs[job_key].update(
                {
                    "status": "generating",
                    "progress": completed_progress,
                    "message": (
                        "Combining audio chunks"
                        if completed_chunks == len(chunks)
                        else f"Processed {completed_chunks} of {len(chunks)} chunks"
                    ),
                    "current_chunk": idx + 1,
                    "completed_chunks": completed_chunks,
                    "total_chunks": len(chunks),
                    "current_chunk_started_monotonic": chunk_started_monotonic,
                    "last_chunk_seconds": round(chunk_elapsed_seconds, 2),
                    "updated_at": _utc_now_iso(),
                }
            )
            logger.info(
                "TTS progress %s chapter %s: finished chunk %s/%s in %.2fs (%.2f%%)",
                novel_slug,
                chapter_number,
                completed_chunks,
                len(chunks),
                chunk_elapsed_seconds,
                completed_progress,
            )
            _save_audio_metadata(
                novel_slug,
                chapter_number,
                voice,
                "generating",
                provider_name=provider_name,
                progress=completed_progress,
            )

            chunk_timings.append(
                {
                    "index": idx,
                    "text": chunk.strip(),
                    "start": round(current_time, 3),
                    "end": round(current_time + duration, 3),
                    "duration": round(duration, 3),
                }
            )
            audio_segments.append(audio)
            current_time += duration + silence_duration

        if not audio_segments:
            raise ValueError("No audio segments were generated")

        combined = []
        for idx, segment in enumerate(audio_segments):
            combined.append(segment)
            if idx < len(audio_segments) - 1:
                combined.append(silence)
        final_audio = np.concatenate(combined)
        total_duration = len(final_audio) / provider.sample_rate

        sf.write(str(audio_path), final_audio, provider.sample_rate)

        timing_payload = {
            "novel_slug": novel_slug,
            "chapter_number": chapter_number,
            "total_duration": round(total_duration, 3),
            "chunk_count": len(chunk_timings),
            "sample_rate": provider.sample_rate,
            "provider": provider.health()["provider"],
            "chunks": chunk_timings,
        }
        _write_timings_json(timing_path, timing_payload)
        _replace_timings(novel_slug, chapter_number, chunk_timings)
        _mark_chapter_audio_path(novel_slug, chapter_number, audio_path)

        audio_url = _relative_audio_url(novel_slug, chapter_number)
        _save_audio_metadata(
            novel_slug,
            chapter_number,
            voice,
            "completed",
            provider_name=provider_name,
            audio_url=audio_url,
            duration=round(total_duration, 3),
            progress=100.0,
            error=None,
        )
        tts_jobs[job_key] = {
            "status": "completed",
            "progress": 100,
            "message": "Audio ready",
            "duration": round(total_duration, 3),
            "audio_url": audio_url,
            "current_chunk": len(chunk_timings),
            "completed_chunks": len(chunk_timings),
            "total_chunks": len(chunk_timings),
            "current_chunk_started_monotonic": None,
            "last_chunk_seconds": tts_jobs.get(job_key, {}).get("last_chunk_seconds"),
            "started_at": existing_job.get("started_at") or _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "started_monotonic": existing_job.get("started_monotonic"),
        }
        logger.info(
            "TTS progress %s chapter %s: audio ready with %s chunks (100%%)",
            novel_slug,
            chapter_number,
            len(chunk_timings),
        )
    except Exception as exc:
        logger.error("TTS generation failed for %s chapter %s: %s", novel_slug, chapter_number, exc, exc_info=True)
        _save_audio_metadata(
            novel_slug,
            chapter_number,
            voice,
            "failed",
            provider_name=provider_name,
            progress=0.0,
            error=str(exc),
        )
        failed_existing_job = tts_jobs.get(job_key, {})
        tts_jobs[job_key] = {
            "status": "failed",
            "progress": 0,
            "error": str(exc),
            "message": "Audio generation failed",
            "current_chunk": failed_existing_job.get("current_chunk"),
            "completed_chunks": failed_existing_job.get("completed_chunks", 0),
            "total_chunks": failed_existing_job.get("total_chunks"),
            "current_chunk_started_monotonic": None,
            "last_chunk_seconds": failed_existing_job.get("last_chunk_seconds"),
            "started_at": failed_existing_job.get("started_at"),
            "updated_at": _utc_now_iso(),
            "started_monotonic": failed_existing_job.get("started_monotonic"),
        }


def split_text_into_chunks(text: str, max_length: int = 500) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text.strip())
    chunks = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) <= max_length:
            chunks.append(para)
            continue

        sentences = re.split(r"(?<=[.!?])\s+", para)
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(current) + len(sentence) + 1 <= max_length:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence
        if current:
            chunks.append(current)

    if chunks:
        return chunks

    words = text.split()
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_length:
            current = (current + " " + word).strip()
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks
