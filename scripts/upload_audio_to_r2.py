"""
Upload generated chapter audio to Cloudflare R2 and sync metadata through the local API.

Environment Variables Required:
- API_URL (defaults to the writable local backend: http://localhost:8001/api)
- AUDIO_DIR (defaults to ./audio)
- R2_AUDIO_ACCOUNT_ID (or legacy R2_ACCOUNT_ID)
- R2_AUDIO_ACCESS_KEY_ID (or legacy R2_ACCESS_KEY)
- R2_AUDIO_SECRET_ACCESS_KEY (or legacy R2_SECRET_KEY)
- R2_AUDIO_BUCKET_NAME (or legacy R2_BUCKET_NAME)
- R2_AUDIO_PUBLIC_URL (optional, or legacy R2_PUBLIC_URL)
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional

import boto3
import httpx
import soundfile as sf
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

R2_AUDIO_ACCOUNT_ID = os.getenv("R2_AUDIO_ACCOUNT_ID") or os.getenv("R2_ACCOUNT_ID", "")
R2_AUDIO_ACCESS_KEY_ID = os.getenv("R2_AUDIO_ACCESS_KEY_ID") or os.getenv("R2_ACCESS_KEY", "")
R2_AUDIO_SECRET_ACCESS_KEY = os.getenv("R2_AUDIO_SECRET_ACCESS_KEY") or os.getenv("R2_SECRET_KEY", "")
R2_AUDIO_BUCKET_NAME = os.getenv("R2_AUDIO_BUCKET_NAME") or os.getenv("R2_BUCKET_NAME", "")
R2_AUDIO_PUBLIC_URL = os.getenv("R2_AUDIO_PUBLIC_URL") or os.getenv("R2_PUBLIC_URL", "")

R2_ENDPOINT = f"https://{R2_AUDIO_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_AUDIO_ACCOUNT_ID else ""
API_URL = os.getenv("API_URL", "http://localhost:8001/api")
AUDIO_ROOT = Path(os.getenv("AUDIO_DIR", str(Path(__file__).resolve().parents[1] / "audio"))).expanduser()

_s3_client = None


def get_s3_client():
    global _s3_client

    if _s3_client is not None:
        return _s3_client

    if not all([R2_AUDIO_ACCOUNT_ID, R2_AUDIO_ACCESS_KEY_ID, R2_AUDIO_SECRET_ACCESS_KEY, R2_AUDIO_BUCKET_NAME]):
        print("[ERROR] R2 audio credentials not configured.")
        print("Required env vars: R2_AUDIO_ACCOUNT_ID, R2_AUDIO_ACCESS_KEY_ID, R2_AUDIO_SECRET_ACCESS_KEY, R2_AUDIO_BUCKET_NAME")
        return None

    _s3_client = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_AUDIO_ACCESS_KEY_ID,
        aws_secret_access_key=R2_AUDIO_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )
    print(f"[OK] R2 audio client initialized for bucket: {R2_AUDIO_BUCKET_NAME}")
    return _s3_client


def get_existing_audio_in_r2(novel_slug: str) -> set[int]:
    client = get_s3_client()
    if not client:
        return set()

    existing: set[int] = set()
    prefix = f"novels/{novel_slug}/audio/"

    try:
        paginator = client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=R2_AUDIO_BUCKET_NAME, Prefix=prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                match = re.search(r"audio/(\d+)\.wav$", obj["Key"])
                if match:
                    existing.add(int(match.group(1)))
    except Exception as exc:
        print(f"[WARN] Could not list existing audio for {novel_slug}: {exc}")

    return existing


def build_public_url(key: str) -> str:
    if R2_AUDIO_PUBLIC_URL:
        return f"{R2_AUDIO_PUBLIC_URL.rstrip('/')}/{key}"
    return f"https://{R2_AUDIO_BUCKET_NAME}.{R2_AUDIO_ACCOUNT_ID}.r2.dev/{key}"


def upload_audio_file(filepath: Path, novel_slug: str, chapter_number: int) -> Optional[dict]:
    client = get_s3_client()
    if not client:
        return None

    key = f"novels/{novel_slug}/audio/{chapter_number:04d}.wav"

    try:
        client.upload_file(
            str(filepath),
            R2_AUDIO_BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": "audio/wav"},
        )
        return {
            "audio_key": key,
            "audio_url": build_public_url(key),
        }
    except Exception as exc:
        print(f"[ERROR] Failed to upload {filepath.name}: {exc}")
        return None


def get_audio_duration(filepath: Path) -> Optional[float]:
    try:
        info = sf.info(str(filepath))
        if info.samplerate and info.frames:
            return round(info.frames / info.samplerate, 3)
    except Exception as exc:
        print(f"[WARN] Could not read duration from {filepath}: {exc}")
    return None


def fetch_existing_audio_status(client: httpx.Client, novel_slug: str, chapter_number: int) -> dict:
    try:
        response = client.get(f"{API_URL}/audio/status/{novel_slug}/{chapter_number}", timeout=30)
        if response.status_code == 200:
            return response.json()
    except Exception as exc:
        print(f"[WARN] Failed to fetch existing audio status for {novel_slug} chapter {chapter_number}: {exc}")
    return {}


def update_audio_storage_metadata(client: httpx.Client, novel_slug: str, chapter_number: int, storage: dict, status_payload: dict, duration: Optional[float]) -> bool:
    payload = {
        "audio_key": storage["audio_key"],
        "audio_url": storage["audio_url"],
        "has_audio": True,
        "status": "completed",
        "audio_provider": status_payload.get("provider") or "kokoro",
        "audio_voice": status_payload.get("voice") or "af_heart",
        "audio_duration": duration if duration is not None else status_payload.get("duration"),
        "audio_progress": 100.0,
        "audio_error": None,
    }

    try:
        response = client.patch(
            f"{API_URL}/chapters/novel/{novel_slug}/{chapter_number}/storage",
            json=payload,
            timeout=30,
        )
        if response.status_code == 200:
            return True
        print(f"[WARN] Metadata update failed for {novel_slug} chapter {chapter_number} (status={response.status_code})")
    except Exception as exc:
        print(f"[ERROR] Failed to update audio metadata for {novel_slug} chapter {chapter_number}: {exc}")
    return False


def scan_audio_folders() -> list[dict]:
    novels: list[dict] = []

    if not AUDIO_ROOT.exists():
        print(f"[ERROR] Audio directory not found: {AUDIO_ROOT}")
        return novels

    for folder in AUDIO_ROOT.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        audio_files = sorted(folder.glob("Chapter_*.wav"))
        if not audio_files:
            continue

        novels.append(
            {
                "slug": folder.name,
                "folder": folder,
                "audio_files": audio_files,
                "audio_count": len(audio_files),
            }
        )
        print(f"[FOUND] {folder.name}: {len(audio_files)} audio files")

    return novels


def upload_novel_audio(novel: dict, http_client: httpx.Client, limit: Optional[int] = None) -> None:
    audio_files = novel["audio_files"][:limit] if limit else novel["audio_files"]
    total = len(audio_files)
    success = 0
    fail = 0
    skipped = 0

    existing_chapters = get_existing_audio_in_r2(novel["slug"])
    print(f"[INFO] Found {len(existing_chapters)} audio files already in R2 for {novel['slug']}")

    for index, filepath in enumerate(audio_files, start=1):
        match = re.search(r"Chapter_(\d+)\.wav$", filepath.name)
        if not match:
            continue

        chapter_number = int(match.group(1))
        if chapter_number in existing_chapters:
            skipped += 1
            if index % 200 == 0 or index == total:
                print(f"  Progress: {index}/{total} (new:{success} skip:{skipped} fail:{fail})")
            continue

        storage = upload_audio_file(filepath, novel["slug"], chapter_number)
        if not storage:
            fail += 1
            continue

        duration = get_audio_duration(filepath)
        status_payload = fetch_existing_audio_status(http_client, novel["slug"], chapter_number)
        if update_audio_storage_metadata(http_client, novel["slug"], chapter_number, storage, status_payload, duration):
            success += 1
        else:
            fail += 1

        if index % 100 == 0 or index == total:
            print(f"  Progress: {index}/{total} (new:{success} skip:{skipped} fail:{fail})")

        time.sleep(0.02)

    print(f"[DONE] {novel['slug']}: {success} new, {skipped} skipped, {fail} failed")


def main():
    print("=" * 60)
    print("  UPLOAD GENERATED AUDIO TO CLOUDFLARE R2")
    print("=" * 60)
    print()

    s3 = get_s3_client()
    if not s3:
        print("\n[SETUP] Please set these environment variables:")
        print("  API_URL=http://localhost:8001/api")
        print("  AUDIO_DIR=audio")
        print("  R2_AUDIO_ACCOUNT_ID=<your cloudflare account id>")
        print("  R2_AUDIO_ACCESS_KEY_ID=<your R2 access key>")
        print("  R2_AUDIO_SECRET_ACCESS_KEY=<your R2 secret key>")
        print("  R2_AUDIO_BUCKET_NAME=<your bucket name>")
        print("  R2_AUDIO_PUBLIC_URL=<public URL if using custom domain>")
        return

    novels = scan_audio_folders()
    if not novels:
        print("[ERROR] No generated audio found.")
        return

    total_audio = sum(novel["audio_count"] for novel in novels)
    print(f"\n[INFO] Found {len(novels)} audio folders with {total_audio} total chapter files")

    response = input("\nProceed with audio upload? (y/n): ").strip().lower()
    if response != "y":
        print("Cancelled.")
        return

    limit_input = input("Limit chapters per novel? (number or 'all'): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else None

    with httpx.Client(timeout=60) as http_client:
        for novel in novels:
            print(f"\n{'=' * 60}")
            print(f"Processing audio: {novel['slug']}")
            print(f"{'=' * 60}")
            upload_novel_audio(novel, http_client, limit=limit)

    print("\n" + "=" * 60)
    print("AUDIO UPLOAD COMPLETE")
    print("=" * 60)
    print("\n[NEXT] Uploaded audio is now served from the read-only deployment through audio_key metadata.")


if __name__ == "__main__":
    main()
