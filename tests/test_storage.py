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


class TestSavePostContent:
    BASE_POST = {
        "author_username": "testuser",
        "author_id": "123456789",
        "created_at": "2024-04-04T14:30:00Z",
        "text": "Hello world",
        "media_files": [],
    }

    def test_save_post_content_text_only(self, tmp_path):
        storage = make_storage(tmp_path)
        path = storage.save_post_content("testuser", "1234567890", self.BASE_POST)
        content = path.read_text(encoding="utf-8")
        assert "Author: @testuser (123456789)" in content
        assert "Posted: 2024-04-04 14:30:00 UTC" in content
        assert "URL: https://x.com/testuser/status/1234567890" in content
        assert "Hello world" in content
        assert "Media:" not in content
        assert "Quoted Tweet:" not in content

    def test_save_post_content_with_media(self, tmp_path):
        storage = make_storage(tmp_path)
        post = {**self.BASE_POST, "media_files": ["1234567890_1.jpg", "1234567890_2.mp4"]}
        path = storage.save_post_content("testuser", "1234567890", post)
        content = path.read_text(encoding="utf-8")
        assert "Media: 2 items" in content
        assert "  - 1234567890_1.jpg" in content
        assert "  - 1234567890_2.mp4" in content
        assert "Quoted Tweet:" not in content
