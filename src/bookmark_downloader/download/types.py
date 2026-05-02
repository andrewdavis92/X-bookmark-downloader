"""Data types for the media download engine."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class MediaItem:
    url: str
    media_type: str
    dest_path: Path
    tweet_id: str


@dataclass
class DownloadResult:
    url: str
    dest_path: Path
    success: bool
    file_size: int
    error: Optional[str]
    attempts: int


@dataclass
class DownloadStats:
    tweet_id: str
    total: int
    succeeded: int
    failed: int
    results: List[DownloadResult]
