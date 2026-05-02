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

    def _bookmark_exists(self, tweet_id: str) -> bool:
        cursor = self._conn.execute(
            "SELECT 1 FROM bookmarks WHERE tweet_id = ?", (tweet_id,)
        )
        return cursor.fetchone() is not None

    def _get_bookmark(self, tweet_id: str) -> Optional[Dict]:
        cursor = self._conn.execute(
            "SELECT * FROM bookmarks WHERE tweet_id = ?", (tweet_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def _upsert_bookmark(self, tweet_id: str, **kwargs) -> None:
        now = datetime.utcnow().isoformat()
        kwargs["updated_at"] = now
        if not self._bookmark_exists(tweet_id):
            kwargs["tweet_id"] = tweet_id
            kwargs.setdefault("author_username", None)
            kwargs.setdefault("author_id", None)
            kwargs["created_at"] = now
            cols = ", ".join(kwargs.keys())
            placeholders = ", ".join("?" for _ in kwargs)
            self._conn.execute(
                f"INSERT INTO bookmarks ({cols}) VALUES ({placeholders})",
                list(kwargs.values()),
            )
        else:
            # Never overwrite identity fields on update
            for field in ("tweet_id", "author_username", "author_id", "created_at"):
                kwargs.pop(field, None)
            setters = ", ".join(f"{k} = ?" for k in kwargs)
            self._conn.execute(
                f"UPDATE bookmarks SET {setters} WHERE tweet_id = ?",
                list(kwargs.values()) + [tweet_id],
            )
        self._conn.commit()

    def _log_history(
        self, tweet_id: str, action: str, details: Optional[str] = None
    ) -> None:
        self._conn.execute(
            "INSERT INTO processing_history (tweet_id, action, details) VALUES (?, ?, ?)",
            (tweet_id, action, details),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class StateManager:
    def __init__(self, config) -> None:
        self._db = Database(config.get_database_path())

    def close(self) -> None:
        self._db.close()

    def is_already_processed(self, tweet_id: str) -> bool:
        bookmark = self._db._get_bookmark(tweet_id)
        return bookmark is not None and bookmark["status"] == "success"

    def mark_processed(
        self,
        tweet_id: str,
        status: str,
        file_paths: List[str],
        media_count: int = 0,
    ) -> None:
        now = datetime.utcnow().isoformat()
        self._db._upsert_bookmark(
            tweet_id,
            status=status,
            media_count=media_count,
            folder_path=str(file_paths[0]) if file_paths else None,
            downloaded_at=now,
        )
        self._db._log_history(tweet_id, "processed", f"media_count={media_count}")

    def mark_failed(
        self, tweet_id: str, error: str, retry_count: int = 0
    ) -> None:
        self._db._upsert_bookmark(
            tweet_id,
            status="failed",
            last_error=error,
            retry_count=retry_count,
        )
        self._db._log_history(tweet_id, "failed", error)

    def update_status(
        self,
        tweet_id: str,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        kwargs: Dict = {"status": status}
        if error is not None:
            kwargs["last_error"] = error
        self._db._upsert_bookmark(tweet_id, **kwargs)
