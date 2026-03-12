"""R2 client for uploading chapter audio to Cloudflare R2."""

import os
import logging
from typing import Optional

import boto3
import httpx
from botocore.config import Config

from .config import (
    R2_AUDIO_ACCOUNT_ID,
    R2_AUDIO_ACCESS_KEY_ID, 
    R2_AUDIO_SECRET_ACCESS_KEY,
    R2_AUDIO_BUCKET_NAME,
    R2_AUDIO_PUBLIC_URL
)

logger = logging.getLogger(__name__)

# R2 endpoint format
R2_ENDPOINT = f"https://{R2_AUDIO_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_AUDIO_ACCOUNT_ID else ""

# Singleton S3 client
_s3_client = None


def get_r2_client():
    """Get or create S3 client for R2."""
    global _s3_client
    
    if _s3_client is not None:
        return _s3_client
    
    if not all([R2_AUDIO_ACCOUNT_ID, R2_AUDIO_ACCESS_KEY_ID, R2_AUDIO_SECRET_ACCESS_KEY]):
        logger.warning("R2 Audio credentials not configured in backend.")
        return None
    
    try:
        _s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_AUDIO_ACCESS_KEY_ID,
            aws_secret_access_key=R2_AUDIO_SECRET_ACCESS_KEY,
            config=Config(
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'standard'}
            )
        )
        logger.info(f"R2 client initialized for bucket: {R2_AUDIO_BUCKET_NAME}")
        return _s3_client
    except Exception as e:
        logger.error(f"Failed to initialize R2 client: {e}")
        return None


def upload_chapter_audio_to_r2(
    audio_bytes: bytes,
    novel_slug: str,
    chapter_number: int,
    content_type: str = "audio/wav"
) -> Optional[str]:
    """
    Upload concatenated chapter audio to R2.
    
    Args:
        audio_bytes: WAV audio as bytes
        novel_slug: Novel identifier
        chapter_number: Chapter number
        content_type: MIME type (default: audio/wav)
    
    Returns:
        Public URL to the uploaded file, or None if upload failed
    """
    client = get_r2_client()
    
    if client is None:
        logger.error("R2 client not available - cannot upload chapter audio")
        return None
    
    # Key format: chapters/{novel_slug}/chapter_{number}.wav
    key = f"chapters/{novel_slug}/chapter_{chapter_number:04d}.wav"
    
    try:
        client.put_object(
            Bucket=R2_AUDIO_BUCKET_NAME,
            Key=key,
            Body=audio_bytes,
            ContentType=content_type,
            CacheControl="public, max-age=31536000"  # Cache for 1 year
        )
        
        # Build public URL
        if R2_AUDIO_PUBLIC_URL:
            url = f"{R2_AUDIO_PUBLIC_URL.rstrip('/')}/{key}"
        else:
            # Default R2 public URL format
            url = f"https://{R2_AUDIO_BUCKET_NAME}.{R2_AUDIO_ACCOUNT_ID}.r2.dev/{key}"
        
        logger.info(f"✓ Uploaded chapter audio to R2: {key} ({len(audio_bytes)} bytes)")
        return url
        
    except Exception as e:
        logger.error(f"R2 upload failed for {key}: {e}")
        return None


def delete_chapter_audio_from_r2(novel_slug: str, chapter_number: int) -> bool:
    """
    Delete chapter audio from R2.
    
    Args:
        novel_slug: Novel identifier
        chapter_number: Chapter number
    
    Returns:
        True if deleted successfully
    """
    client = get_r2_client()
    
    if client is None:
        logger.warning("R2 client not available - cannot delete")
        return False
    
    key = f"chapters/{novel_slug}/chapter_{chapter_number:04d}.wav"
    
    try:
        client.delete_object(Bucket=R2_AUDIO_BUCKET_NAME, Key=key)
        logger.info(f"✓ Deleted from R2: {key}")
        return True
    except Exception as e:
        logger.error(f"R2 delete failed for {key}: {e}")
        return False


def download_audio_from_url(url: str) -> Optional[bytes]:
    """
    Download audio bytes from a URL (used to fetch segment audio for concatenation).
    
    Args:
        url: URL to download from
    
    Returns:
        Audio bytes, or None if download failed
    """
    try:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        if response.status_code == 200:
            return response.content
        else:
            logger.error(f"Failed to download audio from {url}: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error downloading audio from {url}: {e}")
        return None
