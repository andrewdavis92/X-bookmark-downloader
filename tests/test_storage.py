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

    def test_save_post_content_with_quote(self, tmp_path):
        storage = make_storage(tmp_path)
        post = {
            **self.BASE_POST,
            "quoted_tweet_id": "9876543210",
            "quoted_author": "otheruser",
            "quoted_text": "Quoted content",
            "quoted_created_at": "2024-04-04T12:00:00Z",
        }
        path = storage.save_post_content("testuser", "1234567890", post)
        content = path.read_text(encoding="utf-8")
        assert "Quoted Tweet: 9876543210 by @otheruser" in content
        assert "Quoted Link: 1234567890_quoted_1.link" in content
        assert "Quote Author: @otheruser" in content
        assert "Quote Posted: 2024-04-04 12:00:00 UTC" in content
        assert "Quote Text: Quoted content" in content

    def test_save_post_content_overwrites(self, tmp_path):
        storage = make_storage(tmp_path)
        storage.save_post_content("testuser", "1234567890", self.BASE_POST)
        updated = {**self.BASE_POST, "text": "Updated text"}
        path = storage.save_post_content("testuser", "1234567890", updated)
        content = path.read_text(encoding="utf-8")
        assert "Updated text" in content
        assert "Hello world" not in content


class TestCreateQuotedSymlink:
    def test_create_quoted_symlink_relative_path(self, tmp_path):
        storage = make_storage(tmp_path)
        storage.ensure_author_directory("user2")
        (tmp_path / "@user2" / "9876543210.txt").write_text("quoted", encoding="utf-8")

        link = storage.create_quoted_symlink("user1", "1234567890", "user2", "9876543210")

        assert link.is_symlink()
        assert link.readlink() == Path("..") / "@user2" / "9876543210.txt"

    def test_create_quoted_symlink_idempotent(self, tmp_path):
        storage = make_storage(tmp_path)
        storage.create_quoted_symlink("user1", "1234567890", "user2", "9876543210")
        storage.create_quoted_symlink("user1", "1234567890", "user2", "9876543210")  # Must not raise

    def test_create_quoted_symlink_dangling(self, tmp_path):
        storage = make_storage(tmp_path)
        link = storage.create_quoted_symlink("user1", "1234567890", "user2", "9876543210")
        assert link.is_symlink()
        assert not link.exists()  # Target absent — dangling symlink is expected


class TestUpdateAuthorMetadata:
    def test_update_author_metadata_creates(self, tmp_path):
        storage = make_storage(tmp_path)
        storage.update_author_metadata("testuser", "123456789", posts_delta=1, media_delta=2)
        data = json.loads((tmp_path / "@testuser" / "_metadata.json").read_text(encoding="utf-8"))
        assert data["username"] == "@testuser"
        assert data["user_id"] == "123456789"
        assert data["posts_downloaded"] == 1
        assert data["total_media_files"] == 2
        assert data["symlinks_created"] == 0
        assert "first_seen" in data
        assert "last_seen" in data

    def test_update_author_metadata_increments(self, tmp_path):
        storage = make_storage(tmp_path)
        storage.update_author_metadata("testuser", "123456789", posts_delta=1, media_delta=2)
        storage.update_author_metadata("testuser", "123456789", posts_delta=1, media_delta=3, symlinks_delta=1)
        data = json.loads((tmp_path / "@testuser" / "_metadata.json").read_text(encoding="utf-8"))
        assert data["posts_downloaded"] == 2
        assert data["total_media_files"] == 5
        assert data["symlinks_created"] == 1

    def test_update_author_metadata_corrupt_json(self, tmp_path):
        storage = make_storage(tmp_path)
        storage.ensure_author_directory("testuser")
        (tmp_path / "@testuser" / "_metadata.json").write_text("not valid json", encoding="utf-8")
        storage.update_author_metadata("testuser", "123456789")
        data = json.loads((tmp_path / "@testuser" / "_metadata.json").read_text(encoding="utf-8"))
        assert data["username"] == "@testuser"
        assert data["posts_downloaded"] == 1
