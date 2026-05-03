import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bookmark_downloader.storage.local_storage import LocalStorage


def make_storage(tmp_path: Path) -> LocalStorage:
    config = MagicMock()
    config.get_downloads_dir.return_value = tmp_path
    return LocalStorage(config)


class TestGetAuthorFolder:
    def test_get_author_folder(self, tmp_path):
        storage = make_storage(tmp_path)
        assert storage.get_author_folder("testuser") == tmp_path / "@testuser"


class TestGetMediaPath:
    def test_get_media_path(self, tmp_path):
        storage = make_storage(tmp_path)
        result = storage.get_media_path("testuser", "1234567890", 1, "jpg")
        assert result == tmp_path / "@testuser" / "1234567890_1.jpg"


class TestGetQuotedLinkPath:
    def test_get_quoted_link_path(self, tmp_path):
        storage = make_storage(tmp_path)
        result = storage.get_quoted_link_path("testuser", "1234567890", 1)
        assert result == tmp_path / "@testuser" / "1234567890_quoted_1.link"


class TestSanitizeUsername:
    def test_sanitize_username_non_ascii(self, tmp_path):
        storage = make_storage(tmp_path)
        assert storage._sanitize_username("café") == "@cafe"

    def test_sanitize_username_at_prefix(self, tmp_path):
        storage = make_storage(tmp_path)
        assert storage._sanitize_username("@testuser") == "@testuser"


class TestEnsureAuthorDirectory:
    def test_ensure_author_directory_creates(self, tmp_path):
        storage = make_storage(tmp_path)
        folder = storage.ensure_author_directory("testuser")
        assert folder.is_dir()
        assert folder == tmp_path / "@testuser"

    def test_ensure_author_directory_idempotent(self, tmp_path):
        storage = make_storage(tmp_path)
        storage.ensure_author_directory("testuser")
        storage.ensure_author_directory("testuser")  # Must not raise
