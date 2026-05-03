from unittest.mock import MagicMock
from pathlib import Path

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
