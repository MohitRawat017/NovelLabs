"""
Upload Novel Chapters to Cloudflare R2

Uploads chapter content (.txt files) from data/output/ to R2 bucket.
The API will then read content from R2 URLs instead of local filesystem.

Environment Variables Required:
- R2_NOVEL_ACCOUNT_ID
- R2_NOVEL_ACCESS_KEY_ID  
- R2_NOVEL_SECRET_ACCESS_KEY
- R2_NOVEL_BUCKET_NAME
- R2_NOVEL_PUBLIC_URL (optional, for custom domain)

Usage:
    python scripts/upload_novels_to_r2.py
"""

import os
import re
import time
import httpx
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config

# ==================== R2 Configuration ====================

R2_NOVEL_ACCOUNT_ID = os.getenv("R2_NOVEL_ACCOUNT_ID", "")
R2_NOVEL_ACCESS_KEY_ID = os.getenv("R2_NOVEL_ACCESS_KEY_ID", "")
R2_NOVEL_SECRET_ACCESS_KEY = os.getenv("R2_NOVEL_SECRET_ACCESS_KEY", "")
R2_NOVEL_BUCKET_NAME = os.getenv("R2_NOVEL_BUCKET_NAME", "")
R2_NOVEL_PUBLIC_URL = os.getenv("R2_NOVEL_PUBLIC_URL", "")

R2_ENDPOINT = f"https://{R2_NOVEL_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_NOVEL_ACCOUNT_ID else ""

# ==================== API Configuration ====================

API_URL = os.getenv("API_URL", "https://novellabs.onrender.com/api")
DATA_DIR = Path(__file__).parent.parent / "data" / "output"

# ==================== S3 Client ====================

_s3_client = None


def get_s3_client():
    """Get or create S3 client for R2."""
    global _s3_client
    
    if _s3_client is not None:
        return _s3_client
    
    if not all([R2_NOVEL_ACCOUNT_ID, R2_NOVEL_ACCESS_KEY_ID, R2_NOVEL_SECRET_ACCESS_KEY]):
        print("[ERROR] R2 Novel credentials not configured!")
        print("Required env vars: R2_NOVEL_ACCOUNT_ID, R2_NOVEL_ACCESS_KEY_ID, R2_NOVEL_SECRET_ACCESS_KEY")
        return None
    
    _s3_client = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_NOVEL_ACCESS_KEY_ID,
        aws_secret_access_key=R2_NOVEL_SECRET_ACCESS_KEY,
        config=Config(
            signature_version='s3v4',
            retries={'max_attempts': 3, 'mode': 'standard'}
        )
    )
    
    print(f"[OK] R2 Novel client initialized for bucket: {R2_NOVEL_BUCKET_NAME}")
    return _s3_client


def check_chapter_exists_in_r2(novel_slug: str, chapter_number: int) -> bool:
    """
    Check if a chapter already exists in R2.
    Returns True if exists, False otherwise.
    """
    client = get_s3_client()
    if not client:
        return False
    
    key = f"novels/{novel_slug}/chapter_{chapter_number:04d}.txt"
    
    try:
        client.head_object(Bucket=R2_NOVEL_BUCKET_NAME, Key=key)
        return True  # File exists
    except client.exceptions.ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False  # File doesn't exist
        # Other errors - assume doesn't exist to allow upload attempt
        return False


def get_existing_chapters_in_r2(novel_slug: str) -> set:
    """
    Get a set of chapter numbers that already exist in R2 for a novel.
    This is more efficient than checking each chapter individually.
    """
    client = get_s3_client()
    if not client:
        return set()
    
    existing = set()
    prefix = f"novels/{novel_slug}/"
    
    try:
        paginator = client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=R2_NOVEL_BUCKET_NAME, Prefix=prefix)
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    # Extract chapter number from key like "novels/slug/chapter_0001.txt"
                    match = re.search(r'chapter_(\d+)\.txt$', obj['Key'])
                    if match:
                        existing.add(int(match.group(1)))
    except Exception as e:
        print(f"[WARN] Could not list existing chapters: {e}")
    
    return existing


def upload_chapter_to_r2(content: str, novel_slug: str, chapter_number: int) -> Optional[str]:
    """
    Upload chapter content to R2 and return the public URL.
    
    File path in R2: novels/{novel_slug}/chapter_{chapter_number:04d}.txt
    """
    client = get_s3_client()
    if not client:
        return None
    
    # Create key (path in bucket)
    key = f"novels/{novel_slug}/chapter_{chapter_number:04d}.txt"
    
    try:
        client.put_object(
            Bucket=R2_NOVEL_BUCKET_NAME,
            Key=key,
            Body=content.encode('utf-8'),
            ContentType='text/plain; charset=utf-8'
        )
        
        # Return public URL
        if R2_NOVEL_PUBLIC_URL:
            return f"{R2_NOVEL_PUBLIC_URL}/{key}"
        else:
            # Default R2 public URL format (if bucket is public)
            return f"https://{R2_NOVEL_BUCKET_NAME}.{R2_NOVEL_ACCOUNT_ID}.r2.dev/{key}"
    
    except Exception as e:
        print(f"[ERROR] Failed to upload {key}: {e}")
        return None


def get_novels_from_filesystem():
    """Scan local data/output directory for novels"""
    novels = []
    
    if not DATA_DIR.exists():
        print(f"[ERROR] Data directory not found: {DATA_DIR}")
        return novels
    
    for folder in DATA_DIR.iterdir():
        if folder.is_dir() and not folder.name.startswith('.'):
            chapter_files = sorted(folder.glob("Chapter_*.txt"))
            chapter_count = len(chapter_files)
            
            if chapter_count > 0:
                slug = folder.name.lower().replace(' ', '-')
                slug = re.sub(r'[^a-z0-9-]', '', slug)
                
                novels.append({
                    'folder': folder,
                    'slug': slug,
                    'title': folder.name.replace('-', ' ').title(),
                    'chapter_count': chapter_count,
                    'chapter_files': chapter_files
                })
                print(f"[FOUND] {folder.name}: {chapter_count} chapters")
    
    return novels


def read_chapter_content(filepath: Path) -> tuple[str, str, int]:
    """Read chapter file. Returns (title, content, word_count)"""
    with open(filepath, 'r', encoding='utf-8') as f:
        full_content = f.read()
    
    lines = full_content.split('\n')
    title = lines[0].strip() if lines else "Untitled Chapter"
    
    # Content after title and separator
    if len(lines) > 2:
        content = '\n'.join(lines[2:]).strip()
    else:
        content = full_content
    
    word_count = len(content.split())
    
    return title, content, word_count


def update_chapter_content_url(client: httpx.Client, novel_slug: str, chapter_number: int, content_url: str):
    """Update chapter in database with R2 content URL"""
    # This endpoint needs to be created in the API
    payload = {
        "content_url": content_url
    }
    
    try:
        response = client.patch(
            f"{API_URL}/chapters/novel/{novel_slug}/{chapter_number}/content-url",
            json=payload,
            timeout=30
        )
        return response.status_code == 200
    except Exception as e:
        print(f"[ERROR] Failed to update chapter URL: {e}")
        return False


def upload_novel_to_r2(novel: dict, http_client: httpx.Client, limit: Optional[int] = None):
    """Upload all chapters of a novel to R2, skipping already uploaded chapters"""
    chapter_files = novel['chapter_files']
    
    if limit:
        chapter_files = chapter_files[:limit]
    
    total = len(chapter_files)
    success = 0
    fail = 0
    skipped = 0
    total_bytes = 0
    
    # Get existing chapters in R2 to skip re-uploading
    print(f"\n[INFO] Checking existing chapters in R2 for {novel['title']}...")
    existing_chapters = get_existing_chapters_in_r2(novel['slug'])
    print(f"[INFO] Found {len(existing_chapters)} chapters already in R2")
    
    print(f"[INFO] Processing {total} chapters of {novel['title']}...")
    
    for i, filepath in enumerate(chapter_files, 1):
        # Extract chapter number
        match = re.search(r'Chapter_(\d+)', filepath.name)
        if not match:
            continue
        
        chapter_number = int(match.group(1))
        
        # Skip if already exists in R2
        if chapter_number in existing_chapters:
            skipped += 1
            if i % 500 == 0 or i == total:
                print(f"  Progress: {i}/{total} (new:{success} skip:{skipped} fail:{fail})")
            continue
        
        # Read content
        title, content, word_count = read_chapter_content(filepath)
        total_bytes += len(content.encode('utf-8'))
        
        # Upload to R2
        content_url = upload_chapter_to_r2(content, novel['slug'], chapter_number)
        
        if content_url:
            # Update database with the URL
            if update_chapter_content_url(http_client, novel['slug'], chapter_number, content_url):
                success += 1
            else:
                # URL uploaded but DB update failed - still count as partial success
                success += 1
                print(f"[WARN] R2 OK but DB update failed for chapter {chapter_number}")
        else:
            fail += 1
            if fail <= 5:
                print(f"[ERROR] Failed to upload chapter {chapter_number}")
        
        # Progress
        if i % 100 == 0 or i == total:
            mb = total_bytes / 1024 / 1024
            print(f"  Progress: {i}/{total} (new:{success} skip:{skipped} fail:{fail}) | Uploaded: {mb:.1f} MB")
        
        time.sleep(0.02)  # Small delay to avoid rate limiting
    
    mb = total_bytes / 1024 / 1024
    print(f"[DONE] {novel['title']}: {success} new, {skipped} skipped, {fail} failed | Uploaded: {mb:.1f} MB")


def main():
    print("=" * 60)
    print("  UPLOAD NOVELS TO CLOUDFLARE R2")
    print("=" * 60)
    print()
    
    # Check R2 credentials
    s3 = get_s3_client()
    if not s3:
        print("\n[SETUP] Please set these environment variables:")
        print("  R2_NOVEL_ACCOUNT_ID=<your cloudflare account id>")
        print("  R2_NOVEL_ACCESS_KEY_ID=<your R2 access key>")
        print("  R2_NOVEL_SECRET_ACCESS_KEY=<your R2 secret key>")
        print("  R2_NOVEL_BUCKET_NAME=<your bucket name>")
        print("  R2_NOVEL_PUBLIC_URL=<public URL if using custom domain>")
        return
    
    # Scan for novels
    novels = get_novels_from_filesystem()
    
    if not novels:
        print("[ERROR] No novels found in data/output/")
        return
    
    total_chapters = sum(n['chapter_count'] for n in novels)
    estimated_mb = (total_chapters * 10000) / 1024 / 1024
    print(f"\n[INFO] Found {len(novels)} novels with {total_chapters} total chapters")
    print(f"[INFO] Estimated upload size: {estimated_mb:.1f} MB")
    
    # Confirm
    response = input("\nProceed with R2 upload? (y/n): ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        return
    
    # Limit option
    limit_input = input("Limit chapters per novel? (number or 'all'): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else None
    
    # Upload
    with httpx.Client(timeout=60) as http_client:
        for novel in novels:
            print(f"\n{'='*60}")
            print(f"Processing: {novel['title']}")
            print(f"{'='*60}")
            upload_novel_to_r2(novel, http_client, limit=limit)
    
    print("\n" + "=" * 60)
    print("UPLOAD COMPLETE")
    print("=" * 60)
    print("\n[NEXT] Update your API to read from content_url instead of content_path")


if __name__ == "__main__":
    main()
