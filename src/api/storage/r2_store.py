import logging
from functools import lru_cache
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from ..config import (
    R2_AUDIO_ACCESS_KEY_ID,
    R2_AUDIO_ACCOUNT_ID,
    R2_AUDIO_BUCKET_NAME,
    R2_AUDIO_PUBLIC_URL,
    R2_AUDIO_SECRET_ACCESS_KEY,
    R2_NOVEL_ACCESS_KEY_ID,
    R2_NOVEL_ACCOUNT_ID,
    R2_NOVEL_BUCKET_NAME,
    R2_NOVEL_PUBLIC_URL,
    R2_NOVEL_SECRET_ACCESS_KEY,
)

logger = logging.getLogger(__name__)


def _normalize_key(key: str) -> str:
    return key.lstrip("/")


def is_chapter_r2_configured() -> bool:
    return all(
        [
            R2_NOVEL_ACCOUNT_ID,
            R2_NOVEL_ACCESS_KEY_ID,
            R2_NOVEL_SECRET_ACCESS_KEY,
            R2_NOVEL_BUCKET_NAME,
        ]
    )


def is_audio_r2_configured() -> bool:
    return all(
        [
            R2_AUDIO_ACCOUNT_ID,
            R2_AUDIO_ACCESS_KEY_ID,
            R2_AUDIO_SECRET_ACCESS_KEY,
            R2_AUDIO_BUCKET_NAME,
        ]
    )


def is_r2_configured() -> bool:
    return is_chapter_r2_configured()


@lru_cache(maxsize=1)
def _get_chapter_client():
    endpoint_url = f"https://{R2_NOVEL_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=R2_NOVEL_ACCESS_KEY_ID,
        aws_secret_access_key=R2_NOVEL_SECRET_ACCESS_KEY,
        region_name="auto",
    )


@lru_cache(maxsize=1)
def _get_audio_client():
    endpoint_url = f"https://{R2_AUDIO_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=R2_AUDIO_ACCESS_KEY_ID,
        aws_secret_access_key=R2_AUDIO_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def get_chapter_text(key: str, encoding: str = "utf-8") -> Optional[str]:
    if not key:
        return None

    if not is_chapter_r2_configured():
        logger.warning("Chapter R2 is not configured; cannot fetch object key: %s", key)
        return None

    normalized_key = _normalize_key(key)

    try:
        response = _get_chapter_client().get_object(Bucket=R2_NOVEL_BUCKET_NAME, Key=normalized_key)
        payload = response["Body"].read()
        return payload.decode(encoding, errors="replace")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "unknown")
        logger.warning("Failed to fetch chapter R2 object '%s' (code=%s)", normalized_key, code)
        return None
    except Exception as exc:
        logger.warning("Unexpected error fetching chapter R2 object '%s': %s", normalized_key, exc)
        return None


def build_chapter_public_url(key: str) -> Optional[str]:
    if not key:
        return None

    if key.startswith("http://") or key.startswith("https://"):
        return key

    if not R2_NOVEL_PUBLIC_URL:
        return None

    normalized_key = _normalize_key(key)
    return f"{R2_NOVEL_PUBLIC_URL.rstrip('/')}/{normalized_key}"


def build_audio_public_url(key: str) -> Optional[str]:
    if not key:
        return None

    if key.startswith("http://") or key.startswith("https://"):
        return key

    if not R2_AUDIO_PUBLIC_URL:
        return None

    normalized_key = _normalize_key(key)
    return f"{R2_AUDIO_PUBLIC_URL.rstrip('/')}/{normalized_key}"


def get_object_text(key: str, encoding: str = "utf-8") -> Optional[str]:
    return get_chapter_text(key, encoding=encoding)


def build_public_url(key: str) -> Optional[str]:
    return build_chapter_public_url(key)
