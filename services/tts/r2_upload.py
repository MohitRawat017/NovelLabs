"""
R2 Upload Utility for NovelLabs TTS Service

Uploads audio files to Cloudflare R2 and returns public URLs.
R2 is S3-compatible, so we use boto3.

Environment Variables Required:
- R2_AUDIO_ACCOUNT_ID
- R2_AUDIO_ACCESS_KEY_ID
- R2_AUDIO_SECRET_ACCESS_KEY
- R2_AUDIO_BUCKET_NAME
- R2_AUDIO_PUBLIC_URL (optional, for custom domain)
"""

import os
import logging
from typing import Optional

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

# ==================== Configuration ====================

R2_AUDIO_ACCOUNT_ID = os.getenv("R2_AUDIO_ACCOUNT_ID", "")
R2_AUDIO_ACCESS_KEY_ID = os.getenv("R2_AUDIO_ACCESS_KEY_ID", "")
R2_AUDIO_SECRET_ACCESS_KEY = os.getenv("R2_AUDIO_SECRET_ACCESS_KEY", "")
R2_AUDIO_BUCKET_NAME = os.getenv("R2_AUDIO_BUCKET_NAME", "novellabs-audio")
R2_AUDIO_PUBLIC_URL = os.getenv("R2_AUDIO_PUBLIC_URL", "")  # e.g., https://audio.novellabs.com

# R2 endpoint format
R2_ENDPOINT = f"https://{R2_AUDIO_ACCOUNT_ID}.r2.cloudflarestorage.com" if R2_AUDIO_ACCOUNT_ID else ""

# ==================== S3 Client ====================

_s3_client = None


def get_s3_client():
    """Get or create S3 client for R2."""
    global _s3_client
    
    if _s3_client is not None:
        return _s3_client
    
    if not all([R2_AUDIO_ACCOUNT_ID, R2_AUDIO_ACCESS_KEY_ID, R2_AUDIO_SECRET_ACCESS_KEY]):
        logger.warning("R2 Audio credentials not configured. Using mock upload.")
        return None
    
    _s3_client = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_AUDIO_ACCESS_KEY_ID,
        aws_secret_access_key=R2_AUDIO_SECRET_ACCESS_KEY,
        config=Config(
            signature_version='s3v4',
            retries={'max_attempts': 2, 'mode': 'standard'}
        )
    )
    
    logger.info(f"R2 Audio client initialized for bucket: {R2_AUDIO_BUCKET_NAME}")
    return _s3_client


def upload_audio_to_r2(
    audio_bytes: bytes,
    filename: str,
    content_type: str = "audio/wav"
) -> str:
    """
    Upload audio bytes to R2 and return the public URL.
    
    Args:
        audio_bytes: WAV audio as bytes
        filename: Filename to use in R2 (e.g., "seg_123.wav")
        content_type: MIME type (default: audio/wav)
    
    Returns:
        Public URL to the uploaded file
    """
    client = get_s3_client()
    
    # Mock mode for local development
    if client is None:
        mock_url = f"http://localhost:8002/mock-audio/{filename}"
        logger.warning(f"R2 not configured. Mock URL: {mock_url}")
        return mock_url
    
    # Upload to R2
    key = f"audio/{filename}"  # Store in audio/ prefix
    
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
            # Custom domain (recommended for production)
            url = f"{R2_AUDIO_PUBLIC_URL.rstrip('/')}/{key}"
        else:
            # Default R2 public URL format
            url = f"https://{R2_AUDIO_BUCKET_NAME}.{R2_AUDIO_ACCOUNT_ID}.r2.dev/{key}"
        
        logger.info(f"✓ Uploaded to R2: {key}")
        return url
        
    except Exception as e:
        logger.error(f"R2 upload failed: {e}")
        raise RuntimeError(f"Failed to upload audio: {e}")


def delete_audio_from_r2(filename: str) -> bool:
    """
    Delete an audio file from R2.
    
    Args:
        filename: Filename in R2 (e.g., "seg_123.wav")
    
    Returns:
        True if deleted successfully
    """
    client = get_s3_client()
    
    if client is None:
        logger.warning("R2 not configured. Skipping delete.")
        return True
    
    key = f"audio/{filename}"
    
    try:
        client.delete_object(Bucket=R2_AUDIO_BUCKET_NAME, Key=key)
        logger.info(f"✓ Deleted from R2: {key}")
        return True
    except Exception as e:
        logger.error(f"R2 delete failed: {e}")
        return False
