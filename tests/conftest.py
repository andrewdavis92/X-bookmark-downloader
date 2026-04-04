"""Pytest configuration and shared fixtures."""

import os
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def sample_config_yaml(temp_dir) -> Path:
    """Create a sample YAML configuration file."""
    config_file = temp_dir / "config.yaml"
    config_content = """
twitter:
  bearer_token: test_bearer_token_123
  request_timeout: 30

paths:
  downloads_directory: ~/Documents/X-Bookmarks
  logs_directory: ~/Library/Logs/bookmark-downloader

download:
  image_quality: high
  video_quality: best
  max_workers: 4
  timeout_seconds: 600
  retry_attempts: 3

processing:
  follow_quotes: true
  max_quote_depth: 1
  batch_size: 100

state_management:
  database_file: state.db
  tracking_method: local_logging
  retention_days: -1

logging:
  level: INFO
  filename: bookmark_downloader.log
  max_bytes: 10485760
  backup_count: 5

quarantine:
  folder: quarantine
"""
    config_file.write_text(config_content)
    return config_file


@pytest.fixture
def sample_env_file(temp_dir) -> Path:
    """Create a sample .env file."""
    env_file = temp_dir / ".env"
    env_content = """TWITTER_BEARER_TOKEN=test_token_from_env
BOOKMARK_DOWNLOADER_DOWNLOAD_MAX_WORKERS=8
BOOKMARK_DOWNLOADER_LOGGING_LEVEL=DEBUG
"""
    env_file.write_text(env_content)
    return env_file


@pytest.fixture
def clean_env():
    """Fixture to clean up environment variables before and after tests."""
    # Save original environment
    original_env = dict(os.environ)

    # Clear specific environment variables that might interfere
    for key in list(os.environ.keys()):
        if key.startswith("BOOKMARK_DOWNLOADER_") or key == "TWITTER_BEARER_TOKEN":
            del os.environ[key]

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
