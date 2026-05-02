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


_SQL_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""

_SQL_BOOKMARKS = """
CREATE TABLE IF NOT EXISTS bookmarks (
    tweet_id TEXT PRIMARY KEY,
    author_username TEXT,
    author_id TEXT,
    post_text TEXT,
    downloaded_at TIMESTAMP,
    status TEXT CHECK(status IN ('success', 'failed', 'quarantined')),
    media_count INT DEFAULT 0,
    folder_path TEXT,
    removed_from_bookmarks BOOLEAN DEFAULT FALSE,
    last_error TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_SQL_MEDIA_FILES = """
CREATE TABLE IF NOT EXISTS media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    media_type TEXT CHECK(media_type IN ('photo', 'video', 'animated_gif')),
    file_size INT,
    downloaded_at TIMESTAMP,
    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id)
);
"""

_SQL_QUOTED_POSTS = """
CREATE TABLE IF NOT EXISTS quoted_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_tweet_id TEXT NOT NULL,
    quoted_tweet_id TEXT NOT NULL,
    symlink_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_tweet_id) REFERENCES bookmarks(tweet_id)
);
"""

_SQL_PROCESSING_HISTORY = """
CREATE TABLE IF NOT EXISTS processing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    action TEXT CHECK(action IN ('processed', 'skipped', 'failed', 'retried')),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);
"""


class Database:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(_SQL_SCHEMA_VERSION)
        cursor = self._conn.execute("SELECT version FROM schema_version")
        row = cursor.fetchone()
        current_version = row["version"] if row else 0
        if current_version < SCHEMA_VERSION:
            self._run_migrations(current_version)
        self._conn.commit()

    def _run_migrations(self, from_version: int) -> None:
        if from_version < 1:
            self._conn.execute(_SQL_BOOKMARKS)
            self._conn.execute(_SQL_MEDIA_FILES)
            self._conn.execute(_SQL_QUOTED_POSTS)
            self._conn.execute(_SQL_PROCESSING_HISTORY)
            self._conn.execute("DELETE FROM schema_version")
            self._conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
            )

    def close(self) -> None:
        self._conn.close()
