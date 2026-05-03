# Phase 6: Local Storage & File Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `LocalStorage`, a class that manages all filesystem interactions — author directories, post text files, media file paths, quoted-post symlinks, and per-author metadata.

**Architecture:** A single `LocalStorage` class initialized with `Config` (consistent with `StateManager` and `TwitterClient`) exposes pure path helpers and separate side-effect operations. Username sanitization uses `unicodedata` stdlib — no new dependency.

**Tech Stack:** Python 3.9+ stdlib (`pathlib`, `unicodedata`, `re`, `json`, `datetime`), pytest with `tmp_path` fixture (real filesystem, no mocking).

---

## File Map

| File | Action |
|------|--------|
| `src/bookmark_downloader/storage/local_storage.py` | Create |
| `tests/test_storage.py` | Create |

---

### Task 1: Module skeleton, path helpers, and username sanitization

**Files:**
- Create: `src/bookmark_downloader/storage/local_storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `ERROR ... ModuleNotFoundError: No module named 'bookmark_downloader.storage.local_storage'`

- [ ] **Step 3: Create the implementation**

Create `src/bookmark_downloader/storage/local_storage.py`:

```python
"""Local file system storage for X bookmark downloader."""

import re
import unicodedata
from pathlib import Path
from typing import Dict

from bookmark_downloader.config import Config
from bookmark_downloader.utils.logger import get_logger

logger = get_logger(__name__)


class LocalStorage:
    def __init__(self, config: Config) -> None:
        self._downloads_dir = config.get_downloads_dir()

    def _sanitize_username(self, username: str) -> str:
        name = username.lstrip("@")
        name = unicodedata.normalize("NFKD", name)
        name = name.encode("ascii", errors="ignore").decode("ascii")
        name = re.sub(r"[^A-Za-z0-9_]", "", name)
        return "@" + name

    def get_author_folder(self, username: str) -> Path:
        return self._downloads_dir / self._sanitize_username(username)

    def get_post_text_path(self, username: str, post_id: str) -> Path:
        return self.get_author_folder(username) / f"{post_id}.txt"

    def get_media_path(self, username: str, post_id: str, index: int, ext: str) -> Path:
        return self.get_author_folder(username) / f"{post_id}_{index}.{ext}"

    def get_quoted_link_path(self, username: str, post_id: str, quote_index: int) -> Path:
        return self.get_author_folder(username) / f"{post_id}_quoted_{quote_index}.link"
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/bookmark_downloader/storage/local_storage.py
git commit -m "feat(storage): add LocalStorage path helpers and username sanitization"
```

---

### Task 2: `ensure_author_directory`

**Files:**
- Modify: `src/bookmark_downloader/storage/local_storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py` after `TestSanitizeUsername`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_storage.py::TestEnsureAuthorDirectory -v
```

Expected: `FAILED ... AttributeError: 'LocalStorage' object has no attribute 'ensure_author_directory'`

- [ ] **Step 3: Add `ensure_author_directory` to `local_storage.py`**

Add after `get_quoted_link_path`:

```python
    def ensure_author_directory(self, username: str) -> Path:
        folder = self.get_author_folder(username)
        folder.mkdir(parents=True, exist_ok=True)
        return folder
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/bookmark_downloader/storage/local_storage.py
git commit -m "feat(storage): add ensure_author_directory"
```

---

### Task 3: `save_post_content` — text-only posts

**Files:**
- Modify: `src/bookmark_downloader/storage/local_storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run test — verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_storage.py::TestSavePostContent::test_save_post_content_text_only -v
```

Expected: `FAILED ... AttributeError: 'LocalStorage' object has no attribute 'save_post_content'`

- [ ] **Step 3: Add `from datetime import datetime` to imports and add the method**

Add `from datetime import datetime` to the import block at the top of `local_storage.py`. Then add after `ensure_author_directory`:

```python
    def save_post_content(self, username: str, post_id: str, post_data: Dict) -> Path:
        folder = self.ensure_author_directory(username)
        txt_path = folder / f"{post_id}.txt"

        author_username = post_data["author_username"]
        author_id = post_data["author_id"]
        created_at = post_data.get("created_at", "")
        text = post_data["text"]

        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            posted = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, AttributeError):
            posted = created_at

        lines = [
            f"Author: @{author_username} ({author_id})",
            f"Posted: {posted}",
            f"URL: https://x.com/{author_username}/status/{post_id}",
            "",
            text,
        ]

        txt_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("Saved post content for %s to %s", post_id, txt_path)
        return txt_path
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/bookmark_downloader/storage/local_storage.py
git commit -m "feat(storage): add save_post_content for text-only posts"
```

---

### Task 4: `save_post_content` — media section

**Files:**
- Modify: `src/bookmark_downloader/storage/local_storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Append inside `TestSavePostContent` in `tests/test_storage.py`:

```python
    def test_save_post_content_with_media(self, tmp_path):
        storage = make_storage(tmp_path)
        post = {**self.BASE_POST, "media_files": ["1234567890_1.jpg", "1234567890_2.mp4"]}
        path = storage.save_post_content("testuser", "1234567890", post)
        content = path.read_text(encoding="utf-8")
        assert "Media: 2 items" in content
        assert "  - 1234567890_1.jpg" in content
        assert "  - 1234567890_2.mp4" in content
        assert "Quoted Tweet:" not in content
```

- [ ] **Step 2: Run test — verify it fails**

```bash
source .venv/bin/activate && pytest tests/test_storage.py::TestSavePostContent::test_save_post_content_with_media -v
```

Expected: `FAILED ... AssertionError: assert 'Media: 2 items' in ...`

- [ ] **Step 3: Replace `save_post_content` in `local_storage.py` with the media-aware version**

```python
    def save_post_content(self, username: str, post_id: str, post_data: Dict) -> Path:
        folder = self.ensure_author_directory(username)
        txt_path = folder / f"{post_id}.txt"

        author_username = post_data["author_username"]
        author_id = post_data["author_id"]
        created_at = post_data.get("created_at", "")
        text = post_data["text"]
        media_files = post_data.get("media_files", [])

        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            posted = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, AttributeError):
            posted = created_at

        lines = [
            f"Author: @{author_username} ({author_id})",
            f"Posted: {posted}",
            f"URL: https://x.com/{author_username}/status/{post_id}",
            "",
            text,
        ]

        if media_files:
            lines.extend(["", "---"])
            lines.append(f"Media: {len(media_files)} item{'s' if len(media_files) != 1 else ''}")
            for f in media_files:
                lines.append(f"  - {f}")

        txt_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("Saved post content for %s to %s", post_id, txt_path)
        return txt_path
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/bookmark_downloader/storage/local_storage.py
git commit -m "feat(storage): extend save_post_content with media section"
```

---

### Task 5: `save_post_content` — quoted post section and overwrite

**Files:**
- Modify: `src/bookmark_downloader/storage/local_storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append inside `TestSavePostContent`:

```python
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
```

- [ ] **Step 2: Run tests — verify the quote test fails**

```bash
source .venv/bin/activate && pytest tests/test_storage.py::TestSavePostContent -v
```

Expected: `test_save_post_content_with_quote` FAILED, others PASSED.

- [ ] **Step 3: Replace `save_post_content` with the complete final version**

```python
    def save_post_content(self, username: str, post_id: str, post_data: Dict) -> Path:
        folder = self.ensure_author_directory(username)
        txt_path = folder / f"{post_id}.txt"

        author_username = post_data["author_username"]
        author_id = post_data["author_id"]
        created_at = post_data.get("created_at", "")
        text = post_data["text"]
        media_files = post_data.get("media_files", [])
        quoted_tweet_id = post_data.get("quoted_tweet_id")
        quoted_author = post_data.get("quoted_author")
        quoted_text = post_data.get("quoted_text")
        quoted_created_at = post_data.get("quoted_created_at")

        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            posted = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, AttributeError):
            posted = created_at

        lines = [
            f"Author: @{author_username} ({author_id})",
            f"Posted: {posted}",
            f"URL: https://x.com/{author_username}/status/{post_id}",
            "",
            text,
        ]

        has_media = bool(media_files)
        has_quote = bool(quoted_tweet_id)

        if has_media or has_quote:
            lines.extend(["", "---"])

        if has_media:
            lines.append(f"Media: {len(media_files)} item{'s' if len(media_files) != 1 else ''}")
            for f in media_files:
                lines.append(f"  - {f}")

        if has_quote:
            if has_media:
                lines.append("")
            quoted_author_str = f"@{quoted_author}" if quoted_author else quoted_tweet_id
            lines.append(f"Quoted Tweet: {quoted_tweet_id} by {quoted_author_str}")
            lines.append(f"Quoted Link: {post_id}_quoted_1.link")
            lines.append("---")
            if quoted_author:
                lines.append(f"Quote Author: @{quoted_author}")
            if quoted_created_at:
                try:
                    qdt = datetime.fromisoformat(quoted_created_at.replace("Z", "+00:00"))
                    lines.append(f"Quote Posted: {qdt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                except (ValueError, AttributeError):
                    lines.append(f"Quote Posted: {quoted_created_at}")
            if quoted_text:
                lines.append(f"Quote Text: {quoted_text}")

        txt_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("Saved post content for %s to %s", post_id, txt_path)
        return txt_path
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/bookmark_downloader/storage/local_storage.py
git commit -m "feat(storage): extend save_post_content with quoted post section"
```

---

### Task 6: `create_quoted_symlink`

**Files:**
- Modify: `src/bookmark_downloader/storage/local_storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_storage.py::TestCreateQuotedSymlink -v
```

Expected: `FAILED ... AttributeError: 'LocalStorage' object has no attribute 'create_quoted_symlink'`

- [ ] **Step 3: Add `create_quoted_symlink` to `local_storage.py`**

Add after `save_post_content`:

```python
    def create_quoted_symlink(
        self,
        parent_username: str,
        parent_post_id: str,
        quoted_username: str,
        quoted_post_id: str,
        quote_index: int = 1,
    ) -> Path:
        link_path = self.get_quoted_link_path(parent_username, parent_post_id, quote_index)
        self.ensure_author_directory(parent_username)

        if link_path.exists() or link_path.is_symlink():
            logger.debug("Symlink already exists at %s, skipping", link_path)
            return link_path

        quoted_folder = self._sanitize_username(quoted_username)
        target = Path("..") / quoted_folder / f"{quoted_post_id}.txt"
        link_path.symlink_to(target)
        logger.debug("Created symlink %s -> %s", link_path, target)
        return link_path
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_storage.py src/bookmark_downloader/storage/local_storage.py
git commit -m "feat(storage): add create_quoted_symlink"
```

---

### Task 7: `update_author_metadata`

**Files:**
- Modify: `src/bookmark_downloader/storage/local_storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_storage.py::TestUpdateAuthorMetadata -v
```

Expected: `FAILED ... AttributeError: 'LocalStorage' object has no attribute 'update_author_metadata'`

- [ ] **Step 3: Add `import json` to imports in `local_storage.py` and add the method**

Add `import json` to the import block at the top. Then add after `create_quoted_symlink`:

```python
    def update_author_metadata(
        self,
        username: str,
        user_id: str,
        posts_delta: int = 1,
        media_delta: int = 0,
        symlinks_delta: int = 0,
    ) -> None:
        folder = self.ensure_author_directory(username)
        metadata_path = folder / "_metadata.json"
        now = datetime.utcnow().isoformat()
        sanitized = self._sanitize_username(username)

        try:
            existing = (
                json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata_path.exists()
                else None
            )
        except (json.JSONDecodeError, OSError):
            existing = None

        if existing is None:
            metadata = {
                "username": sanitized,
                "user_id": user_id,
                "first_seen": now,
                "last_seen": now,
                "posts_downloaded": posts_delta,
                "total_media_files": media_delta,
                "symlinks_created": symlinks_delta,
            }
        else:
            metadata = existing
            metadata["last_seen"] = now
            metadata["posts_downloaded"] = existing.get("posts_downloaded", 0) + posts_delta
            metadata["total_media_files"] = existing.get("total_media_files", 0) + media_delta
            metadata["symlinks_created"] = existing.get("symlinks_created", 0) + symlinks_delta

        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        logger.debug("Updated metadata for %s", sanitized)
```

- [ ] **Step 4: Run all storage tests — verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_storage.py -v
```

Expected: `17 passed`

- [ ] **Step 5: Run full suite — check for regressions**

```bash
source .venv/bin/activate && pytest -v
```

Expected: all previously passing tests still pass plus the 17 new storage tests.

- [ ] **Step 6: Commit**

```bash
git add tests/test_storage.py src/bookmark_downloader/storage/local_storage.py
git commit -m "feat(storage): add update_author_metadata"
```
