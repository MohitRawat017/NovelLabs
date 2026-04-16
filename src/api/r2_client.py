"""Compatibility shim for legacy R2 client.

This module remains at the old import path to avoid breaking external scripts.
For new code, prefer `src.api.storage.r2_store`.
"""

from .legacy.r2_client import *  # noqa: F401,F403

