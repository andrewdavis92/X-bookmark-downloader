from unittest.mock import MagicMock
from pathlib import Path
import json

from bookmark_downloader.api.twitter_client import RateLimitError
from bookmark_downloader.storage.quarantine import (
    ErrorCategory,
    QuarantineManager,
    classify_error,
)


def make_quarantine_manager(tmp_path: Path) -> QuarantineManager:
    config = MagicMock()
    config.get_quarantine_dir.return_value = tmp_path / "quarantine"
    return QuarantineManager(config)


def test_classify_error_categories():
    assert classify_error(RateLimitError("rate limit")) == ErrorCategory.RETRIABLE
    assert classify_error(TimeoutError()) == ErrorCategory.RETRIABLE
    assert classify_error(ConnectionError()) == ErrorCategory.RETRIABLE
    assert classify_error(ValueError("API error 500: server error")) == ErrorCategory.RETRIABLE
    assert classify_error(ValueError("API error 503: unavailable")) == ErrorCategory.RETRIABLE
    assert classify_error(ValueError("API error 404: not found")) == ErrorCategory.PERMANENT
    assert classify_error(ValueError("API error 403: forbidden")) == ErrorCategory.PERMANENT
    assert classify_error(ValueError("Missing required field: id")) == ErrorCategory.PERMANENT
    assert classify_error(PermissionError()) == ErrorCategory.PERMANENT
    assert classify_error(OSError()) == ErrorCategory.PERMANENT
    assert classify_error(RuntimeError("unexpected")) == ErrorCategory.PERMANENT


def test_get_item_dir(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    assert qm.get_item_dir("tweet_123") == tmp_path / "quarantine" / "tweet_123"


def test_quarantine_item_creates_dir(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_123", None, ValueError("bad"), ErrorCategory.PERMANENT)
    assert (tmp_path / "quarantine" / "tweet_123").is_dir()


def test_quarantine_item_writes_error_txt(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item(
        "tweet_123", None, ValueError("bad tweet"), ErrorCategory.PERMANENT, retry_count=2
    )
    content = (tmp_path / "quarantine" / "tweet_123" / "error.txt").read_text()
    assert "Tweet ID:    tweet_123" in content
    assert "Category:    permanent" in content
    assert "Error Type:  ValueError" in content
    assert "Error:       bad tweet" in content
    assert "Retry Count: 2" in content
    assert "Quarantined:" in content


def test_quarantine_item_writes_tweet_json(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    data = {"id": "tweet_123", "text": "hello"}
    qm.quarantine_item("tweet_123", data, ValueError("bad"), ErrorCategory.PERMANENT)
    tweet_json = tmp_path / "quarantine" / "tweet_123" / "tweet.json"
    assert tweet_json.exists()
    assert json.loads(tweet_json.read_text()) == data


def test_quarantine_item_no_tweet_json_when_none(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_123", None, ValueError("bad"), ErrorCategory.PERMANENT)
    assert not (tmp_path / "quarantine" / "tweet_123" / "tweet.json").exists()


def test_quarantine_item_idempotent(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_123", None, ValueError("first"), ErrorCategory.PERMANENT)
    qm.quarantine_item("tweet_123", None, ValueError("second"), ErrorCategory.PERMANENT)
    content = (tmp_path / "quarantine" / "tweet_123" / "error.txt").read_text()
    assert "second" in content
