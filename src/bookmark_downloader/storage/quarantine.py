"""Quarantine management for failed bookmark processing."""

import json
import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from bookmark_downloader.api.twitter_client import RateLimitError
from bookmark_downloader.config import Config
from bookmark_downloader.utils.logger import get_logger

logger = get_logger(__name__)


class ErrorCategory(Enum):
    RETRIABLE = "retriable"
    PERMANENT = "permanent"
    SKIP = "skip"


def classify_error(exc: Exception) -> ErrorCategory:
    """Classify an exception as RETRIABLE or PERMANENT. Never returns SKIP."""
    if isinstance(exc, RateLimitError):
        return ErrorCategory.RETRIABLE
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ErrorCategory.RETRIABLE
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "500" in msg or "503" in msg:
            return ErrorCategory.RETRIABLE
        return ErrorCategory.PERMANENT
    if isinstance(exc, (PermissionError, OSError)):
        return ErrorCategory.PERMANENT
    return ErrorCategory.PERMANENT


class QuarantineManager:
    def __init__(self, config: Config) -> None:
        self._quarantine_dir = config.get_quarantine_dir()
