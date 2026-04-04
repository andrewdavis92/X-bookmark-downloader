# CLAUDE.md — AI Assistant Guide for X-Bookmark-Downloader

## Project Status

**Pre-implementation.** The codebase currently contains only the planning document (`PLAN.md`) and configuration files. No source code has been written yet. The `PLAN.md` is the authoritative specification — consult it for detailed requirements before writing any code.

---

## What This Project Does

A Python CLI application that automatically downloads media from X (Twitter) bookmarks:
- Fetches bookmarks via X API v2 (requires elevated access + OAuth 2.0)
- Downloads images and videos (using yt-dlp for video)
- Organizes files by creator username with flat per-author directories
- Tracks processed items in SQLite to prevent duplicates
- Quarantines failed items for later retry
- Runs on macOS via launchd scheduler

---

## Planned Project Structure

```
X-bookmark-downloader/
├── src/bookmark_downloader/
│   ├── main.py                   # Orchestrator / CLI entry point
│   ├── config.py                 # Config loading (env > .env > yaml > defaults)
│   ├── api/
│   │   ├── twitter_client.py     # X API wrapper, bookmark pagination
│   │   └── auth.py               # OAuth 2.0 handling
│   ├── download/
│   │   ├── media_handler.py      # Detect & coordinate media downloads
│   │   ├── image_downloader.py   # httpx-based image download + retry
│   │   └── video_downloader.py   # yt-dlp wrapper
│   ├── processing/
│   │   ├── post_processor.py     # Extract metadata, detect media
│   │   └── quote_resolver.py     # Quoted post handling + symlink creation
│   ├── storage/
│   │   ├── local_storage.py      # File organization, directory creation
│   │   ├── database.py           # SQLite CRUD layer
│   │   └── quarantine.py         # Quarantine management
│   └── utils/
│       ├── logger.py             # Rotating file logger setup
│       └── helpers.py            # Shared utilities
├── schedule/
│   └── com.user.bookmark-downloader.plist  # macOS launchd config
├── tests/
│   ├── conftest.py               # pytest fixtures
│   ├── test_api.py
│   ├── test_download.py
│   ├── test_storage.py
│   └── test_state.py
├── requirements.txt
├── setup.py
├── .env.example
├── config.example.yaml
├── config.example.json
├── PLAN.md                       # Full implementation specification
└── CLAUDE.md                     # This file
```

---

## Technology Stack

| Component | Library | Why |
|-----------|---------|-----|
| Language | Python 3.9+ | Rich ecosystem, rapid dev |
| X API | tweepy ≥ 4.14.0 | Official client, OAuth, pagination |
| Video download | yt-dlp ≥ 2024.01.01 | Active maintenance, format/quality selection |
| HTTP client | httpx ≥ 0.24.0 | Modern, async-capable, timeout support |
| Config | PyYAML + python-dotenv | Standard config pattern |
| State DB | SQLite3 (stdlib) | No server, single-user, reliable |
| Testing | pytest + pytest-cov | Industry standard |
| Scheduler | macOS launchd | Native macOS integration |

**`requirements.txt` contents (planned):**
```
tweepy>=4.14.0
yt-dlp>=2024.01.01
httpx>=0.24.0
pyyaml>=6.0
python-dotenv>=1.0.0
pytest>=7.0.0
pytest-cov>=4.0.0
```

---

## Development Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Set TWITTER_BEARER_TOKEN in .env

# Configure paths
cp config.example.yaml config.yaml
# Set downloads_directory and logs_directory

# Verify setup
python -m bookmark_downloader verify_setup

# Test run (5 bookmarks)
python -m bookmark_downloader download --limit 5
```

**Required environment variable:**
```
TWITTER_BEARER_TOKEN=<X API bearer token>   # CRITICAL — nothing works without this
```

**X API requirement:** Elevated access required for bookmark endpoints.

---

## CLI Commands

```bash
python -m bookmark_downloader download [--limit N] [--log-level DEBUG]
python -m bookmark_downloader retry_quarantine [--limit 10]
python -m bookmark_downloader show_stats
python -m bookmark_downloader verify_setup
python -m bookmark_downloader clear_cache
python -m bookmark_downloader quarantine_status
python -m bookmark_downloader clear_quarantine [--older-than 30]
```

---

## Configuration System

Priority (highest → lowest): environment variables → `.env` file → `config.yaml`/`config.json` → hardcoded defaults.

**Key config sections:**
```yaml
twitter:
  bearer_token: ${TWITTER_BEARER_TOKEN}
  request_timeout: 30

paths:
  downloads_directory: ~/Documents/X-Bookmarks   # media organized by author
  logs_directory: ~/Library/Logs/bookmark-downloader  # logs + state DB + quarantine

download:
  image_quality: high
  video_quality: best
  max_workers: 4
  timeout_seconds: 600
  retry_attempts: 3

processing:
  follow_quotes: true
  max_quote_depth: 1   # NEVER recurse deeper than 1 level
  batch_size: 100

state_management:
  database_file: state.db   # relative to logs_directory
  tracking_method: local_logging   # or 'bookmark_removal' or 'hybrid'
  retention_days: 90

logging:
  level: INFO
  filename: bookmark_downloader.log
  max_bytes: 10485760
  backup_count: 5

quarantine:
  folder: quarantine   # relative to logs_directory
```

**Path resolution rules:**
- `~/` → expanded to home directory
- `./` → relative to config file directory
- Absolute paths used as-is
- All directories created automatically on first run

---

## File Organization Conventions

### Output Directory Structure

```
~/Documents/X-Bookmarks/       (downloads_directory)
├── @username_1/
│   ├── 1234567890.txt                   # Post metadata + text content
│   ├── 1234567890_1.jpg                 # First media item (1-indexed)
│   ├── 1234567890_2.mp4                 # Second media item
│   ├── 1234567890_quoted_1.link         # Symlink → quoted post media
│   ├── _metadata.json                   # Author-level statistics
│   └── ...
└── _processing_summary.json             # Overall run statistics
```

### Filename Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Post text | `{post_id}.txt` | `1234567890.txt` |
| Media files | `{post_id}_{index}.{ext}` | `1234567890_1.jpg` |
| Quoted symlinks | `{parent_id}_quoted_{index}.link` | `1234567890_quoted_1.link` |
| Author metadata | `_metadata.json` | `_metadata.json` |

- Media index is **1-indexed** (starts at 1, not 0)
- Symlinks target: `../../../@other_user/{quoted_id}_{media_index}.{ext}`
- Underscore prefix (`_`) means special/aggregate file

### Post Text File Format

```
Author: @username (123456789)
Posted: 2024-04-04 14:30:00 UTC
URL: https://x.com/username/status/1234567890

[Full post text]

---
Metrics: 1.2K Likes, 342 Retweets, 89 Replies

Media: 3 items
  - 1234567890_1.jpg
  - 1234567890_2.mp4

Quoted Tweet: 9876543210 by @other_user
Symlink: 1234567890_quoted_1.link -> ../../../@other_user/9876543210_1.jpg
```

---

## Database Schema

```sql
CREATE TABLE bookmarks (
    tweet_id TEXT PRIMARY KEY,
    author_username TEXT NOT NULL,
    author_id TEXT NOT NULL,
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

CREATE TABLE media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    media_type TEXT CHECK(media_type IN ('photo', 'video', 'animated_gif')),
    file_size INT,
    downloaded_at TIMESTAMP,
    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id)
);

CREATE TABLE quoted_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_tweet_id TEXT NOT NULL,
    quoted_tweet_id TEXT NOT NULL,
    symlink_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_tweet_id) REFERENCES bookmarks(tweet_id),
    FOREIGN KEY (quoted_tweet_id) REFERENCES bookmarks(tweet_id)
);

CREATE TABLE processing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    action TEXT CHECK(action IN ('processed', 'skipped', 'failed', 'retried')),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);
```

---

## Error Handling Strategy

Three categories — never conflate them:

| Category | Trigger | Action |
|----------|---------|--------|
| **Retriable** | 429, 500-503, timeout, partial download | Exponential backoff: 3 attempts at 2s / 4s / 8s |
| **Quarantine** | 404, 403/401, corrupted file, missing required data | Move to quarantine folder with metadata JSON |
| **Skip** | Missing optional metadata, deleted quote post | Log warning, continue |

### Quarantine Folder Structure

```
quarantine/
├── failed_items.json       # Index of all failures
├── 2024-04-04/
│   ├── 1234567890.json     # Failure metadata per tweet
│   └── errors.log
└── retry_log.txt
```

---

## Key Code Patterns

### Module Responsibilities (Single Concern)
- `config.py` — load & validate configuration only
- `twitter_client.py` — API calls only; no business logic
- `post_processor.py` — parse tweet data; no I/O
- `media_handler.py` — coordinate downloads; delegate to image/video modules
- `database.py` — SQLite CRUD only; no business logic
- `local_storage.py` — filesystem operations only

### StateManager Interface (implement exactly this)

```python
class StateManager:
    def mark_processed(self, tweet_id: str, status: str, file_paths: List[str], media_count: int = 0) -> None: ...
    def mark_failed(self, tweet_id: str, error: str, retry_count: int = 0) -> None: ...
    def is_already_processed(self, tweet_id: str) -> bool: ...
    def get_failed_bookmarks(self, limit: int = 100) -> List[Dict]: ...
    def get_processing_stats(self) -> ProcessingStats: ...
    def clear_old_entries(self, days: int = 90) -> int: ...
```

### API Client Interface (key methods)

```python
def get_bookmarks(max_results: int, pagination_token: str | None) -> List[Tweet]: ...
def get_tweet_details(tweet_id: str, expansions: List[str]) -> Tweet: ...
def extract_media_urls(tweet_data: dict) -> List[MediaUrl]: ...
def is_rate_limited(self) -> bool: ...
def wait_for_rate_limit_reset(self) -> None: ...
```

---

## Testing Conventions

- Framework: **pytest** with fixtures in `conftest.py`
- Coverage target: **>80%** for core modules (`api/`, `download/`, `storage/`, `processing/`)
- Mock all external I/O: API calls (mock tweepy), HTTP (mock httpx), yt-dlp
- Test files mirror source structure: `test_api.py` → `api/`, etc.
- Integration tests use real filesystem with `tmp_path` fixture

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src/bookmark_downloader --cov-report=term-missing

# Specific module
pytest tests/test_api.py -v
```

---

## Processing Flow (implement in this order)

```
1. Load config → init logging
2. Init SQLite state DB
3. Authenticate via OAuth 2.0 (Bearer token)
4. Fetch bookmarks page (100 max per request)
5. For each bookmark:
   a. Skip if already in state DB (is_already_processed)
   b. Extract metadata (author, timestamp, text, media_keys)
   c. Detect media (photos, videos, animated GIFs, external URLs)
   d. Download media with retry logic → save to @username/ directory
   e. If has quoted tweet: fetch it, download its media, create symlinks
   f. Write {post_id}.txt with metadata
   g. Update state DB (mark_processed or mark_failed/quarantine)
6. Paginate until no more results
7. Write _processing_summary.json
```

---

## Important Constraints

- **Quote depth:** Never exceed 1 level of quote resolution (`max_quote_depth: 1`)
- **No bookmark deletion by default:** Default tracking method is `local_logging`, not `bookmark_removal`
- **macOS-specific features:** launchd scheduler and `~/Library/` paths are macOS-only — do not assume cross-platform
- **No web framework:** This is a pure CLI application; do not introduce Flask/FastAPI/etc.
- **No media format conversion:** Download in original format; do not transcode
- **No deletion of local media:** The app never deletes downloaded files
- **UTF-8 encoding:** All text files must be written with UTF-8 encoding

---

## Git Conventions

- Default branch: `main`
- Feature/task branches follow pattern: `claude/<description>-<id>`
- Commit messages are descriptive and imperative (e.g., `Add SQLite state management module`)
