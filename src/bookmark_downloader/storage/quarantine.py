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

    def get_item_dir(self, tweet_id: str) -> Path:
        return self._quarantine_dir / tweet_id

    def quarantine_item(
        self,
        tweet_id: str,
        tweet_data: Optional[Dict],
        error: Exception,
        error_category: ErrorCategory,
        retry_count: int = 0,
    ) -> Path:
        item_dir = self.get_item_dir(tweet_id)
        item_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        error_content = (
            f"Tweet ID:    {tweet_id}\n"
            f"Quarantined: {now}\n"
            f"Category:    {error_category.value}\n"
            f"Error Type:  {type(error).__name__}\n"
            f"Error:       {error}\n"
            f"Retry Count: {retry_count}\n"
        )
        (item_dir / "error.txt").write_text(error_content, encoding="utf-8")

        if tweet_data is not None:
            (item_dir / "tweet.json").write_text(
                json.dumps(tweet_data, indent=2), encoding="utf-8"
            )

        logger.debug("Quarantined tweet %s (category=%s)", tweet_id, error_category.value)
        return item_dir

    def get_tweet_data(self, tweet_id: str) -> Optional[Dict]:
        tweet_json = self.get_item_dir(tweet_id) / "tweet.json"
        if not tweet_json.exists():
            return None
        try:
            return json.loads(tweet_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def remove_item(self, tweet_id: str) -> None:
        item_dir = self.get_item_dir(tweet_id)
        if item_dir.exists():
            shutil.rmtree(item_dir)
            logger.debug("Removed quarantine item %s", tweet_id)

    def list_quarantined_ids(self) -> List[str]:
        if not self._quarantine_dir.exists():
            return []
        return [
            entry.name
            for entry in self._quarantine_dir.iterdir()
            if entry.is_dir()
        ]

    def generate_report(self, results: List[Dict]) -> Path:
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        report_path = self._quarantine_dir / f"quarantine_report_{timestamp}.txt"

        succeeded = [r for r in results if r["outcome"] == "success"]
        failed = [r for r in results if r["outcome"] == "failed"]

        header_date = now.strftime("%Y-%m-%dT%H:%M:%S")
        title = f"Quarantine Retry Report — {header_date}"
        lines = [
            title,
            "=" * len(title),
            f"Retried:   {len(results)}",
            f"Succeeded: {len(succeeded)}",
            f"Failed:    {len(failed)}",
        ]

        if failed:
            lines += ["", "FAILURES", "--------"]
            for r in failed:
                lines += [
                    f"Tweet ID:    {r.get('tweet_id', 'unknown')}",
                    f"  Category:    {r.get('error_category', 'unknown')}",
                    f"  Error:       {r.get('error', 'unknown')}",
                    f"  Retry Count: {r.get('retry_count', '?')}",
                    "",
                ]

        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("Generated quarantine report at %s", report_path)
        return report_path
