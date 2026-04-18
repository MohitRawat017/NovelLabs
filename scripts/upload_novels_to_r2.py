"""
Upload Novel Chapters to Cloudflare R2
=======================================

Uploads chapter content (.txt files) from data/output/ to R2 bucket.
Uses deterministic keys so the backend resolves content by convention
with zero database round trips.

R2 key format: {novel-slug}/Chapter_{NNNN}.txt
Existing objects are overwritten (idempotent).
Uploads are concurrent (10 workers by default).

Environment Variables Required:
  R2_NOVEL_ACCOUNT_ID        (or legacy R2_ACCOUNT_ID)
  R2_NOVEL_ACCESS_KEY_ID     (or legacy R2_ACCESS_KEY)
  R2_NOVEL_SECRET_ACCESS_KEY (or legacy R2_SECRET_KEY)
  R2_NOVEL_BUCKET_NAME       (or legacy R2_BUCKET_NAME)

Usage:
    python scripts/upload_novels_to_r2.py
"""

import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

# ==================== R2 Configuration ====================

R2_NOVEL_ACCOUNT_ID = os.getenv("R2_NOVEL_ACCOUNT_ID") or os.getenv("R2_ACCOUNT_ID", "")
R2_NOVEL_ACCESS_KEY_ID = os.getenv("R2_NOVEL_ACCESS_KEY_ID") or os.getenv("R2_ACCESS_KEY", "")
R2_NOVEL_SECRET_ACCESS_KEY = os.getenv("R2_NOVEL_SECRET_ACCESS_KEY") or os.getenv("R2_SECRET_KEY", "")
R2_NOVEL_BUCKET_NAME = os.getenv("R2_NOVEL_BUCKET_NAME") or os.getenv("R2_BUCKET_NAME", "")

R2_ENDPOINT = (
    f"https://{R2_NOVEL_ACCOUNT_ID}.r2.cloudflarestorage.com"
    if R2_NOVEL_ACCOUNT_ID
    else ""
)

DATA_DIR = Path(__file__).parent.parent / "data" / "output"
MAX_WORKERS = int(os.getenv("UPLOAD_WORKERS", "10"))

# ==================== S3 Client ====================

_s3_client = None


def get_s3_client():
    """Get or create the threadsafe R2 boto3 client."""
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    if not all([R2_NOVEL_ACCOUNT_ID, R2_NOVEL_ACCESS_KEY_ID, R2_NOVEL_SECRET_ACCESS_KEY]):
        print("[ERROR] R2 credentials not configured!")
        print("Required: R2_NOVEL_ACCOUNT_ID, R2_NOVEL_ACCESS_KEY_ID, R2_NOVEL_SECRET_ACCESS_KEY")
        return None

    _s3_client = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_NOVEL_ACCESS_KEY_ID,
        aws_secret_access_key=R2_NOVEL_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )
    print(f"[OK] R2 client ready — bucket: {R2_NOVEL_BUCKET_NAME}")
    return _s3_client


# ==================== Key Convention ====================

def make_key(novel_slug: str, chapter_number: int) -> str:
    """Canonical R2 key matching the backend convention."""
    return f"{novel_slug}/Chapter_{chapter_number:04d}.txt"


# ==================== Single Chapter Upload ====================

def upload_one(novel_slug: str, filepath: Path) -> tuple[int, bool, str]:
    """
    Upload a single chapter file. Returns (chapter_number, success, message).
    Thread-safe — boto3 S3 clients support concurrent use.
    """
    m = re.search(r"Chapter_(\d+)", filepath.name)
    if not m:
        return (0, False, f"Bad filename: {filepath.name}")

    chapter_number = int(m.group(1))

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            full_content = f.read()
    except Exception as exc:
        return (chapter_number, False, f"Read error: {exc}")

    # Strip title line + separator — upload clean prose only
    lines = full_content.split("\n")
    if len(lines) > 2:
        body = "\n".join(lines[2:]).strip()
    else:
        body = full_content.strip()

    if not body:
        return (chapter_number, False, "Empty content")

    key = make_key(novel_slug, chapter_number)
    client = get_s3_client()

    try:
        client.put_object(
            Bucket=R2_NOVEL_BUCKET_NAME,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        return (chapter_number, True, key)
    except Exception as exc:
        return (chapter_number, False, f"R2 error: {exc}")


# ==================== Slug Derivation ====================

def slugify(name: str) -> str:
    """Match the backend's slugify logic."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


# ==================== Filesystem Scan ====================

def get_novels_from_filesystem() -> list[dict]:
    """Scan data/output/ for novel folders with Chapter_*.txt files."""
    if not DATA_DIR.exists():
        print(f"[ERROR] Data directory not found: {DATA_DIR}")
        return []

    novels = []
    for folder in sorted(DATA_DIR.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue

        chapter_files = sorted(folder.glob("Chapter_*.txt"))
        if not chapter_files:
            continue

        slug = slugify(folder.name)
        novels.append({
            "folder": folder,
            "slug": slug,
            "title": folder.name,
            "chapter_count": len(chapter_files),
            "chapter_files": chapter_files,
        })
        print(f"[FOUND] {folder.name} → slug='{slug}' ({len(chapter_files)} chapters)")

    return novels


# ==================== Upload Novel ====================

def upload_novel(novel: dict, limit: Optional[int] = None):
    """Upload all chapters concurrently. No API calls — R2 only."""
    chapter_files = novel["chapter_files"]
    if limit:
        chapter_files = chapter_files[:limit]

    total = len(chapter_files)
    success = 0
    fail = 0
    start_time = time.monotonic()

    print(f"\n[UPLOAD] {novel['title']} — {total} chapters, {MAX_WORKERS} workers")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(upload_one, novel["slug"], fp): fp
            for fp in chapter_files
        }

        for i, future in enumerate(as_completed(futures), 1):
            chapter_num, ok, msg = future.result()
            if ok:
                success += 1
            else:
                fail += 1
                if fail <= 10:
                    print(f"  [FAIL] Chapter {chapter_num}: {msg}")

            if i % 50 == 0 or i == total:
                elapsed = time.monotonic() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                print(
                    f"  Progress: {i}/{total} "
                    f"(ok:{success} fail:{fail}) "
                    f"[{rate:.0f} ch/s, {elapsed:.1f}s elapsed]",
                    flush=True,
                )

    elapsed = time.monotonic() - start_time
    print(f"[DONE] {novel['title']}: {success} uploaded, {fail} failed in {elapsed:.1f}s")


# ==================== Main ====================

def main():
    print("=" * 64)
    print("  UPLOAD NOVELS TO CLOUDFLARE R2  (deterministic keys)")
    print("=" * 64)
    print()
    print(f"  R2 bucket  : {R2_NOVEL_BUCKET_NAME}")
    print(f"  Key format : {{slug}}/Chapter_{{NNNN}}.txt")
    print(f"  Workers    : {MAX_WORKERS} concurrent")
    print(f"  Overwrite  : YES (always)")
    print(f"  API calls  : NONE (backend resolves keys by convention)")
    print()

    if not get_s3_client():
        print("\n[SETUP] Required env vars:")
        print("  R2_NOVEL_ACCOUNT_ID")
        print("  R2_NOVEL_ACCESS_KEY_ID")
        print("  R2_NOVEL_SECRET_ACCESS_KEY")
        print("  R2_NOVEL_BUCKET_NAME")
        sys.exit(1)

    novels = get_novels_from_filesystem()
    if not novels:
        print("[ERROR] No novels found in data/output/")
        sys.exit(0)

    total_chapters = sum(n["chapter_count"] for n in novels)
    print(f"\n[INFO] {len(novels)} novel(s), {total_chapters} total chapters")

    response = input("\nProceed? (y/n): ").strip().lower()
    if response != "y":
        print("Cancelled.")
        sys.exit(0)

    limit_input = input("Limit chapters per novel? (number or Enter for all): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else None

    overall_start = time.monotonic()

    for novel in novels:
        print(f"\n{'=' * 64}")
        print(f"  {novel['title']}")
        print(f"{'=' * 64}")
        upload_novel(novel, limit=limit)

    overall_elapsed = time.monotonic() - overall_start
    print(f"\n{'=' * 64}")
    print(f"  ALL UPLOADS COMPLETE — {overall_elapsed:.1f}s total")
    print(f"{'=' * 64}")
    print()
    print("  The backend resolves chapter text from R2 by convention:")
    print(f"    GET /api/chapters/novel/{{slug}}/{{number}}")
    print(f"    → R2 key: {{slug}}/Chapter_{{NNNN}}.txt")
    print()
    print("  No database updates needed.")


if __name__ == "__main__":
    main()
