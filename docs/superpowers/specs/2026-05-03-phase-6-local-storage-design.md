# Phase 6: Local Storage & File Organization — Design Spec

**Date:** 2026-05-03
**Status:** Approved
**Depends on:** Phase 1 (config), Phase 3 (state management)

---

## Goal

Implement `local_storage.py` — the module responsible for all filesystem interactions: creating author directories, writing post text files, generating media file paths, creating quoted-post symlinks, and maintaining per-author `_metadata.json` files.

---

## Scope

**In scope:**
- `storage/local_storage.py` with a `LocalStorage` class
- `tests/test_storage.py` with 17 tests

**Out of scope:**
- Downloading media (Phase 4)
- `_processing_summary.json` at downloads root (Phase 8)
- Recording `quoted_posts` DB relationships (Phase 8)
- Quarantine management (Phase 7)

---

## Architecture

### Design decision: Option A — `LocalStorage` class

Consistent with `StateManager` and `TwitterClient` — a class initialized with `Config`, exposing pure path helpers and side-effect operations as separate methods. Uses stdlib `unicodedata` and `re` for username sanitization; no new dependency.

### Files

| File | Change |
|------|--------|
| `src/bookmark_downloader/storage/local_storage.py` | New — `LocalStorage` class |
| `tests/test_storage.py` | New — storage tests |

No other files change.

---

## `storage/local_storage.py`

### Public interface

```python
class LocalStorage:
    def __init__(self, config: Config) -> None

    # Pure path helpers — no I/O
    def get_author_folder(self, username: str) -> Path
    def get_post_text_path(self, username: str, post_id: str) -> Path
    def get_media_path(self, username: str, post_id: str, index: int, ext: str) -> Path
    def get_quoted_link_path(self, username: str, post_id: str, quote_index: int) -> Path

    # Side-effect operations
    def ensure_author_directory(self, username: str) -> Path
    def save_post_content(self, username: str, post_id: str, post_data: Dict) -> Path
    def create_quoted_symlink(
        self,
        parent_username: str,
        parent_post_id: str,
        quoted_username: str,
        quoted_post_id: str,
        quote_index: int = 1,
    ) -> Path
    def update_author_metadata(
        self,
        username: str,
        user_id: str,
        posts_delta: int = 1,
        media_delta: int = 0,
        symlinks_delta: int = 0,
    ) -> None
```

---

## Username Sanitization

`_sanitize_username` is a private method. All four path helpers call it internally — callers always pass raw usernames and never think about sanitization.

```python
def _sanitize_username(self, username: str) -> str:
    name = username.lstrip("@")
    # Slugify: decompose unicode to ASCII approximations
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", errors="ignore").decode("ascii")
    # Strip anything not in [A-Za-z0-9_]
    name = re.sub(r"[^A-Za-z0-9_]", "", name)
    return "@" + name
```

The `@` prefix is always re-added so directory names match the `@username` convention from the plan.

---

## Directory Structure

```
{downloads_dir}/
├── @username_1/                          # get_author_folder("username_1")
│   ├── 1234567890.txt                    # get_post_text_path("username_1", "1234567890")
│   ├── 1234567890_1.jpg                  # get_media_path("username_1", "1234567890", 1, "jpg")
│   ├── 1234567890_2.mp4                  # get_media_path("username_1", "1234567890", 2, "mp4")
│   ├── 1234567890_quoted_1.link          # get_quoted_link_path("username_1", "1234567890", 1)
│   └── _metadata.json
└── @username_2/
    ├── 9876543210.txt
    └── _metadata.json
```

`ensure_author_directory` calls `mkdir(parents=True, exist_ok=True)` and returns the path. It is idempotent and safe to call multiple times per post.

---

## Post Text Format

`save_post_content` writes UTF-8, overwriting any existing file (idempotent). It calls `ensure_author_directory` internally.

### `post_data` dict shape

```python
{
    "author_username": str,           # without @
    "author_id": str,
    "created_at": str,                # ISO 8601 from API
    "text": str,
    "media_files": List[str],         # ["1234567890_1.jpg", ...] — may be empty
    "quoted_tweet_id": Optional[str],
    "quoted_author": Optional[str],   # without @
    "quoted_text": Optional[str],
    "quoted_created_at": Optional[str],
}
```

### Output format

```
Author: @username (123456789)
Posted: 2024-04-04 14:30:00 UTC
URL: https://x.com/username/status/1234567890

Full post text here, preserving line breaks
and formatting exactly as received.

---
Media: 2 items
  - 1234567890_1.jpg
  - 1234567890_2.mp4

Quoted Tweet: 9876543210 by @other_user
Quoted Link: 1234567890_quoted_1.link
---
Quote Author: @other_user
Quote Posted: 2024-04-04 12:00:00 UTC
Quote Text: quoted content here
```

### Format rules

- The `Media:` section is omitted entirely if `media_files` is empty
- The `Quoted Tweet:` / `Quoted Link:` / `Quote *:` block is omitted if `quoted_tweet_id` is absent
- `Quoted Link:` filename is derived deterministically from `post_id` and `quote_index=1`
- `Quote Posted:` is omitted if `quoted_created_at` is absent
- No Metrics section (public metrics not requested from API)

---

## Symlinks

### `create_quoted_symlink`

Creates a relative symlink from the parent post's directory to the quoted post's `.txt` file. Since all author directories are siblings under the downloads root, the relative target is always one level up:

```
@user1/1234567890_quoted_1.link  →  ../@user2/9876543210.txt
```

Implementation rules:
- If the symlink already exists, skip silently (idempotent)
- If the target `.txt` doesn't exist yet (quoted tweet not yet processed), create the symlink anyway — a dangling symlink resolves when the quoted tweet is later downloaded
- Uses `Path.symlink_to()` with a relative `Path` target

---

## `_metadata.json`

### Schema

```json
{
  "username": "@username",
  "user_id": "123456789",
  "first_seen": "2024-04-04T14:30:00",
  "last_seen": "2024-04-06T18:30:00",
  "posts_downloaded": 15,
  "total_media_files": 23,
  "symlinks_created": 3
}
```

### `update_author_metadata` behaviour

1. Read `_metadata.json` if it exists
2. Increment counter fields by the provided delta values
3. Set `last_seen` to `datetime.utcnow().isoformat()`
4. Set `first_seen` once on creation, never overwrite
5. Write back as formatted JSON
6. If the file is missing or contains corrupt JSON, recreate from scratch

---

## Error Handling

| Operation | Error | Behaviour |
|---|---|---|
| `ensure_author_directory` | `PermissionError` | Propagate — orchestrator quarantines the post |
| `save_post_content` | `OSError` on write | Propagate |
| `create_quoted_symlink` | Symlink already exists | Skip silently |
| `create_quoted_symlink` | `PermissionError` | Propagate |
| `update_author_metadata` | Corrupt JSON | Recreate file from scratch |
| `update_author_metadata` | `OSError` on write | Propagate |

No module-level error swallowing. Errors that prevent data being saved propagate to the Phase 8 orchestrator, which owns quarantine logic.

---

## Testing Strategy

All tests use `tmp_path` (real filesystem, temp directory). No filesystem mocking.

| Test | What it checks |
|---|---|
| `test_get_author_folder` | Path includes sanitized `@username` under downloads root |
| `test_get_media_path` | Returns `@user/post_1.jpg` for index 1, ext `jpg` |
| `test_get_quoted_link_path` | Returns `@user/post_quoted_1.link` |
| `test_sanitize_username_non_ascii` | `é` → `e`, strips non-`[A-Za-z0-9_]` remainder |
| `test_sanitize_username_at_prefix` | Strips leading `@`, re-adds it |
| `test_ensure_author_directory_creates` | Directory exists after call |
| `test_ensure_author_directory_idempotent` | Second call doesn't raise |
| `test_save_post_content_text_only` | Correct format, no Media/Quoted section |
| `test_save_post_content_with_media` | Media section lists all files |
| `test_save_post_content_with_quote` | Quoted block present, link filename correct |
| `test_save_post_content_overwrites` | Second call overwrites file |
| `test_create_quoted_symlink_relative_path` | Target resolves to `../@user2/post.txt` |
| `test_create_quoted_symlink_idempotent` | Second call skips, no error |
| `test_create_quoted_symlink_dangling` | Symlink created even if target absent |
| `test_update_author_metadata_creates` | New file has correct schema |
| `test_update_author_metadata_increments` | Counters add up across two calls |
| `test_update_author_metadata_corrupt_json` | Recreates file cleanly |

---

## Orchestrator Integration (Phase 8 contract)

Phase 6 ships before Phase 8 exists. The Phase 8 orchestrator must:

1. Construct `LocalStorage(config)` once at startup alongside `StateManager` and `TwitterClient`
2. For each successfully processed tweet:
   - Call `ensure_author_directory(username)` before any writes
   - Pass `post_data` dict with all available fields to `save_post_content`
   - For each downloaded media file, use `get_media_path` to determine the destination path before calling the download engine
   - If `quoted_tweet_id` is present, call `create_quoted_symlink` — the symlink may be dangling if the quoted tweet hasn't been processed yet; it resolves automatically when it is
   - Call `update_author_metadata` with the correct deltas after all files are written
