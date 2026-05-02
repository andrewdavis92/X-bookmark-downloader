"""SQLite state management for X Bookmark Downloader."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

SCHEMA_VERSION = 1


@dataclass
class ProcessingStats:
    total_processed: int
    total_failed: int
    total_quarantined: int
    total_media_downloaded: int
    last_run_at: Optional[str]
