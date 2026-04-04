# X Bookmark Downloader - Implementation Plan

## Table of Contents
1. [Project Overview](#project-overview)
2. [Requirements & Scope](#requirements--scope)
3. [Architecture & Design](#architecture--design)
4. [Project Structure](#project-structure)
5. [Implementation Phases](#implementation-phases)
6. [Technology Stack](#technology-stack)
7. [Detailed Module Specifications](#detailed-module-specifications)
8. [Data Storage & Organization](#data-storage--organization)
9. [State Management](#state-management)
10. [Error Handling](#error-handling)
11. [Scheduling & Deployment](#scheduling--deployment)
12. [Testing Strategy](#testing-strategy)
13. [Critical Path Dependencies](#critical-path-dependencies)
14. [Edge Cases & Gaps](#edge-cases--gaps)

---

## Project Overview

**Goal:** Automatically download media from X (Twitter) bookmarks, organizing files by creator with support for quoted posts and robust error handling.

**Key Features:**
- Fetch bookmarks from X API (v2 elevated access)
- Download images and videos automatically
- Handle multiple media items per post
- Follow quoted posts (one level only)
- Organize downloads by creator username
- Track processed bookmarks to avoid duplicates
- Quarantine failed items for manual review
- Run on macOS via launchd scheduler

**Execution Model:** 
- Command-line Python application
- Scheduled via macOS launchd (cron equivalent)
- Manual CLI for debugging and recovery

---

## Requirements & Scope

### Core Requirements (MVP)
✅ Fetch bookmarks from X API  
✅ Download all image media  
✅ Download all video media (using yt-dlp)  
✅ Handle multiple media per post  
✅ Process quoted posts (one level, store under original author)  
✅ Track processed items (avoid reprocessing)  
✅ Flexible: support bookmark removal OR local logging  
✅ Organize by creator username → post ID → media files  
✅ Quarantine failed items for review  
✅ Save post content as text file  
✅ Create symlinks from parent post to quoted post  

### Future Features (Post-MVP)
- Email/Slack notifications with summary reports
- Comprehensive error recovery workflows
- Dashboard/statistics viewer
- Web interface for quarantine review
- Automatic retry scheduling for quarantined items

### Out of Scope
- Interactive authentication UI (CLI-based only)
- Deletion of local media
- Support for DMs or private accounts beyond bookmarks
- Media format conversion

---

## Architecture & Design

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Application Entry Point                  │
│                      (main.py - Orchestrator)               │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   ┌─────────┐  ┌────────┐  ┌──────────┐
   │  Config │  │  State │  │ API      │
   │ Manager │  │Manager │  │Client    │
   └────┬────┘  └───┬────┘  └────┬─────┘
        │           │             │
        │      ┌────┴─────────────┘
        │      │
        ▼      ▼
   ┌──────────────────────┐
   │  Post Processor      │
   │  - Extract metadata  │
   │  - Detect media      │
   │  - Handle quotes     │
   └──────┬───────────────┘
          │
     ┌────┴───────────────────────┐
     │                            │
     ▼                            ▼
┌──────────────┐          ┌──────────────────┐
│Media Handler │          │Quote Resolver    │
│- Download    │          │- Fetch quote data│
│- Retry logic │          │- Create symlinks │
└──────┬───────┘          └────┬─────────────┘
       │                       │
       └───────────┬───────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ Storage Manager │
          │ - Organize      │
          │ - Write files   │
          │ - Create dirs   │
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │ Update State DB │
          │ - Mark complete │
          │ - Log errors    │
          └─────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Language** | Python 3.9+ | Rapid development, rich libraries, active community |
| **API Client** | tweepy | Official X library, OAuth support, pagination handling |
| **Video Download** | yt-dlp | Active maintenance, quality selection, format flexibility |
| **State Persistence** | SQLite | Lightweight, no server, perfect for single-user, cross-platform |
| **Scheduler** | macOS launchd | Native integration, simple plist config, reliable |
| **File Organization** | By username → post ID | Logical grouping, easy navigation, prevents duplicates |
| **Quote Linking** | Symlinks | Native OS integration, maintains relationships, no duplication |
| **Error Handling** | Quarantine system | Non-destructive, allows manual review and retry |

---

## Project Structure

```
X-bookmark-downloader/
├── PLAN.md                           # This file
├── README.md                          # Project overview
├── requirements.txt                   # Python dependencies
├── setup.py                           # Package configuration
├── .env.example                       # Example environment variables
├── config.example.yaml                # Example YAML configuration
├── config.example.json                # Example JSON configuration
├── .gitignore                         # Git exclusions
│
├── src/
│   └── bookmark_downloader/
│       ├── __init__.py
│       ├── main.py                   # Application entry point & orchestrator
│       ├── config.py                 # Configuration management
│       │
│       ├── api/
│       │   ├── __init__.py
│       │   ├── twitter_client.py     # X API wrapper & bookmarks fetching
│       │   └── auth.py               # Authentication & OAuth handling
│       │
│       ├── download/
│       │   ├── __init__.py
│       │   ├── media_handler.py      # Detect & coordinate media downloads
│       │   ├── image_downloader.py   # Image download with retry logic
│       │   └── video_downloader.py   # yt-dlp wrapper for video downloads
│       │
│       ├── processing/
│       │   ├── __init__.py
│       │   ├── post_processor.py     # Extract post metadata & media refs
│       │   └── quote_resolver.py     # Handle quoted posts & create symlinks
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── local_storage.py      # File organization & directory structure
│       │   ├── database.py           # SQLite state tracking
│       │   └── quarantine.py         # Quarantine management & recovery
│       │
│       └── utils/
│           ├── __init__.py
│           ├── logger.py             # Logging configuration
│           └── helpers.py            # Utility functions
│
├── schedule/
│   └── com.user.bookmark-downloader.plist   # macOS launchd configuration
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # pytest fixtures & configuration
│   ├── test_api.py                   # API client tests
│   ├── test_download.py              # Media download tests
│   ├── test_storage.py               # Storage & organization tests
│   └── test_state.py                 # State management tests
│
└── [Runtime-created directories - configured in config file]
    ├── logs_directory/               # Logs, state DB, quarantine (configurable)
    │   ├── bookmark_downloader.log
    │   ├── state.db
    │   └── quarantine/
    └── downloads_directory/          # Downloaded media by creator (configurable)
        ├── @username_1/
        └── @username_2/
```

---

## Implementation Phases

### Phase 1: Foundation (Setup & Configuration)
**Duration:** 2-3 hours  
**Deliverables:** Project structure, config system, environment setup

**Tasks:**
- [ ] Create directory structure
- [ ] Initialize Python package (setup.py, __init__.py)
- [ ] Create requirements.txt with base dependencies
- [ ] Implement config.py (env var + yaml + defaults)
- [ ] Create .env.example template
- [ ] Set up logging infrastructure (logger.py)
- [ ] Create basic CLI entry point (main.py skeleton)

**Dependencies:** None (foundation phase)

---

### Phase 2: API Integration & Authentication
**Duration:** 3-4 hours  
**Deliverables:** X API client, authentication, bookmark fetching

**Tasks:**
- [ ] Implement twitter_client.py with:
  - OAuth 2.0 authentication flow
  - Bookmark fetching with pagination
  - Tweet detail expansion (media, quotes)
  - Rate limit detection & handling
  - Error handling & retry logic
- [ ] Implement auth.py for credential management
- [ ] Create API response parsing utilities
- [ ] Add rate limit monitoring

**Key Methods:**
```python
get_bookmarks(max_results, pagination_token) -> List[Tweet]
get_tweet_details(tweet_id, expansions) -> Tweet
extract_media_urls(tweet_data) -> List[MediaUrl]
is_rate_limited() -> bool
wait_for_rate_limit_reset() -> None
```

**Dependencies:** Phase 1 (config)

**Critical Blockers:**
- X API v2 elevated access required
- OAuth credentials needed in .env

---

### Phase 3: State Management & Deduplication
**Duration:** 2-3 hours  
**Deliverables:** SQLite database, processing state tracking

**Tasks:**
- [ ] Design database schema (see [State Management](#state-management))
- [ ] Implement database.py with:
  - Database initialization
  - CRUD operations
  - Transaction handling
  - Connection pooling
- [ ] Implement state_manager.py with:
  - mark_processed()
  - is_already_processed()
  - get_failed_items()
  - update_status()
- [ ] Create database migrations/schema versioning

**Dependencies:** Phase 1 (config)

---

### Phase 4: Media Download Engine
**Duration:** 4-5 hours  
**Deliverables:** Image & video downloaders with retry logic

**Tasks:**
- [ ] Implement image_downloader.py:
  - Streaming download with timeout
  - Exponential backoff retry (3 attempts)
  - Filename preservation/sanitization
  - Size validation
  
- [ ] Implement video_downloader.py (yt-dlp wrapper):
  - Direct video URL download
  - External platform detection (YouTube, TikTok, etc.)
  - Quality selection (best available)
  - Format conversion to mp4
  - Post-processing (rename to post_id.mp4)

- [ ] Implement media_handler.py:
  - Media type detection from tweet data
  - Coordinate image/video downloads
  - Handle multiple media per post
  - Collect download statistics

**Key Methods:**
```python
download_image(url, dest_path, tweet_id) -> bool
download_video(url, dest_path, tweet_id) -> bool
detect_media_types(tweet_data) -> List[MediaType]
coordinate_downloads(media_list) -> DownloadStats
```

**Dependencies:** Phase 1 (config), Phase 3 (state)

---

### Phase 5: Quote Post Handling
**Duration:** 2-3 hours  
**Deliverables:** Quote resolver, quote metadata, symlink coordination

**Tasks:**
- [ ] Implement quote_resolver.py:
  - Detect quoted tweets in API response
  - Fetch quoted tweet details (one level only)
  - Extract quoted post media information
  - Return quote metadata (post_id, author, media count)
  
- [ ] Return quote information to main processor:
  - Pass quoted post data to storage manager
  - Coordinate with symlink creation in Phase 6
  - Handle quote deletion edge case (log warning, continue)

**Key Methods:**
```python
resolve_quoted_post(tweet_id, api_client) -> Optional[QuotedPost]
get_quote_metadata(tweet_data) -> Dict {
    'quoted_post_id': str,
    'quoted_author': str,
    'quoted_text': str,
    'media_count': int
}
```

**Data Structure:**
```python
QuotedPost = {
    'post_id': '9876543210',
    'author': '@username_2',
    'text': 'quoted content...',
    'media_urls': [...]
}
```

**Dependencies:** Phase 2 (API), Phase 4 (media)

---

### Phase 6: Local Storage & File Organization
**Duration:** 2-3 hours  
**Deliverables:** File system organization, directory creation, symlinks

**Tasks:**
- [ ] Implement local_storage.py:
  - Create author directories (by username)
  - Sanitize usernames for filesystem (non-ASCII handling)
  - Generate media filenames with post_id prefix
  - Write post content as .txt files
  - Create author-level metadata files
  - Create symlinks for quoted posts

- [ ] Implement post text storage:
  - Format: Author, date, URL, content, media list
  - Handle very long text (> 65KB)
  - Proper encoding (UTF-8)
  - Include media references and quoted post info

- [ ] Implement quoted post symlink creation:
  - Create symlinks from parent post to quoted post media
  - Handle multiple media items in quoted posts
  - Symlink naming: `quoted_link_{parent_id}_to_{quoted_id}`

**Key Methods:**
```python
get_author_folder(username: str) -> Path
get_post_text_path(username: str, post_id: str) -> Path
# Returns: /path/to/@username/1234567890.txt
get_media_path(username: str, post_id: str, index: int, ext: str) -> Path
# Returns: /path/to/@username/1234567890_1.jpg
get_quoted_link_path(username: str, post_id: str, quote_index: int) -> Path
# Returns: /path/to/@username/1234567890_quoted_1.link
ensure_author_directory(username: str) -> Path
save_post_content(author_folder: Path, post_id: str, post_data: Dict) -> None
create_symlink_to_quoted(
    parent_username: str, 
    parent_post_id: str, 
    quoted_username: str, 
    quoted_post_id: str,
    quote_index: int
) -> None
# Creates: {parent_post_id}_quoted_{quote_index}.link -> quoted media
create_metadata_file(author_folder: Path, metadata: Dict) -> None
```

**Dependencies:** Phase 1 (config), Phase 3 (state)

---

### Phase 7: Error Handling & Quarantine System
**Duration:** 2-3 hours  
**Deliverables:** Quarantine management, error classification, recovery tools

**Tasks:**
- [ ] Implement quarantine.py:
  - Create quarantine folder structure
  - Store failed item metadata (JSON)
  - Classify errors (retriable vs permanent)
  - Generate quarantine reports

- [ ] Implement error handling strategy:
  - Classify errors into categories
  - Retry retriable errors with backoff
  - Move permanent failures to quarantine
  - Log detailed error information

- [ ] Implement recovery mechanisms:
  - Command to retry quarantined items
  - Manual quarantine review tools
  - Quarantine status reporting

**Error Categories:**
1. **Retriable** (429, 500, 503, timeout) - Retry with backoff
2. **Quarantine** (404, 403, invalid data) - Manual review
3. **Skip** (non-essential metadata) - Log & continue

**Dependencies:** Phase 1 (config), Phase 3 (state), Phase 4 (download)

---

### Phase 8: Main Application Orchestrator
**Duration:** 3-4 hours  
**Deliverables:** Core application logic, orchestration, CLI

**Tasks:**
- [ ] Implement main.py:
  - Load configuration
  - Initialize API client
  - Check rate limits
  - Fetch bookmarks (paginated)
  - Process each bookmark:
    - Check deduplication
    - Extract metadata
    - Detect media
    - Create directories
    - Download media (with retry)
    - Handle quotes
    - Save metadata
    - Update state
  - Collect statistics
  - Handle errors & quarantine
  - Cleanup temporary files

- [ ] Implement CLI interface:
  ```
  python -m bookmark_downloader [command] [options]
  
  Commands:
    download              Full bookmark download
    retry_quarantine      Retry failed items
    show_stats           Display statistics
    verify_setup         Check configuration
    clear_cache          Remove old data
  ```

- [ ] Implement graceful shutdown:
  - Handle SIGTERM, SIGINT
  - Save partial progress
  - Close database connections
  - Clean up incomplete files

**Main Loop Pseudocode:**
```python
def main():
    config = load_config()
    setup_logging()
    
    stats = ProcessingStats()
    
    try:
        api = TwitterClient(config)
        state = StateManager(config)
        storage = LocalStorage(config)
        
        pagination_token = None
        while True:
            bookmarks, pagination_token = api.get_bookmarks(
                max_results=100,
                pagination_token=pagination_token
            )
            
            for tweet in bookmarks:
                if state.is_already_processed(tweet.id):
                    continue
                
                try:
                    process_tweet(tweet, api, state, storage, stats)
                except Exception as e:
                    quarantine_failed_item(tweet, e, config)
            
            if not pagination_token:
                break
        
        generate_summary(stats)
        
    except RateLimitError:
        api.wait_for_rate_limit_reset()
        retry_with_backoff()
```

**Dependencies:** All previous phases (2-7)

---

### Phase 9: macOS Scheduling & Deployment
**Duration:** 1-2 hours  
**Deliverables:** launchd configuration, installation scripts

**Tasks:**
- [ ] Create launchd plist file:
  - Set up schedule (e.g., daily at 6 AM, 2 PM, 10 PM)
  - Configure environment variables
  - Set up logging to files
  - Handle errors gracefully

- [ ] Create installation/setup script:
  - Copy plist to ~/Library/LaunchAgents/
  - Load launchd job
  - Verify installation
  - Create necessary directories

- [ ] Add documentation:
  - How to install
  - How to check logs
  - How to disable/enable
  - Troubleshooting guide

**launchd Schedule Examples:**
- Hourly: `StartInterval: 3600`
- Specific times: Use `StartCalendarInterval` array
- Every 30 min: `StartInterval: 1800`

**Dependencies:** Phase 8 (main app)

---

### Phase 10: Testing & Quality Assurance
**Duration:** 3-4 hours  
**Deliverables:** Unit tests, integration tests, test coverage

**Tasks:**
- [ ] Write unit tests:
  - API response parsing
  - Media type detection
  - Quote post resolution
  - File path generation
  - State management CRUD
  - Error classification

- [ ] Write integration tests:
  - Full flow with mocked API
  - State persistence & recovery
  - Quarantine workflow
  - Multi-phase processing

- [ ] Manual testing:
  - API authentication
  - Bookmark fetching (real API)
  - Media downloads (real files)
  - Quote post handling
  - Rate limit handling
  - Error scenarios
  - Symlink creation

**Test Coverage Goals:** >80% for core modules

**Dependencies:** All phases

---

## Technology Stack

| Component | Technology | Justification |
|-----------|-----------|---------------|
| **Language** | Python 3.9+ | Rapid development, rich ecosystem |
| **API Client** | tweepy | Official X library, OAuth, pagination |
| **Video Download** | yt-dlp | Active maintenance, quality selection |
| **HTTP Client** | httpx | Async support, modern API, timeouts |
| **Database** | SQLite3 | Lightweight, no server, single-user |
| **Configuration** | PyYAML + python-dotenv | Standard config pattern |
| **Logging** | Python logging | Built-in, proven, rotation support |
| **Scheduler** | macOS launchd | Native, simple plist config |
| **Testing** | pytest | Industry standard, fixtures, plugins |

**Key Dependencies:**
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

## Detailed Module Specifications

### Config Management (`config.py`)

**Loads from (in priority order):**
1. Environment variables
2. `.env` file
3. `config.yaml` file (or `config.json`)
4. Hardcoded defaults

**Configuration Items:**
```yaml
twitter:
  bearer_token: ${TWITTER_BEARER_TOKEN}
  request_timeout: 30

paths:
  # Downloads directory - stores organized bookmarks by creator
  downloads_directory: ~/Documents/X-Bookmarks
  
  # Logs directory - stores application logs, quarantine data, and state database
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
  # Database file location (can be relative or absolute)
  database_file: state.db
  tracking_method: local_logging  # or 'bookmark_removal' or 'hybrid'
  retention_days: 90

logging:
  level: INFO
  # Log file path (relative to logs_directory unless absolute path given)
  filename: bookmark_downloader.log
  max_bytes: 10485760
  backup_count: 5
  
quarantine:
  # Quarantine folder location (relative to logs_directory unless absolute path given)
  folder: quarantine
```

**Path Resolution Rules:**
- Paths starting with `~/` are expanded to user home directory
- Paths starting with `./` are relative to config file directory
- Absolute paths (`/` or drive letter on Windows) are used as-is
- `logs_directory` is the base for: logs, quarantine data, state database
- `downloads_directory` is the base for: organized bookmarks by creator
- All paths are created automatically if they don't exist

### Media Detection (`media_handler.py`)

**Detects from tweet data:**
- Direct photos (photo media type)
- Videos (video media type)
- Animated GIFs (animated_gif media type)
- External URLs (YouTube, TikTok, Instagram, etc.)
- Variant selection (choose highest bitrate)

**Media Detection Process:**
```python
1. Check tweet.attachments.media_keys
2. Cross-reference with includes.media array
3. For each media:
   - Identify type (photo, video, animated_gif)
   - Extract URL(s)
   - Select best variant (by bitrate for video)
4. Extract external_urls from entities
5. Detect external platforms for yt-dlp
```

### Post Text Storage

**File:** `{post_id}.txt`  
**Location:** `{username}/{post_id}.txt`

**Format:**
```
Author: @username (123456789)
Posted: 2024-04-04 14:30:00 UTC
URL: https://x.com/username/status/1234567890

[Full post text here, preserving line breaks and formatting]

---
Metrics: 1.2K Likes, 342 Retweets, 89 Replies

Media: 3 items
  - 1234567890_1.jpg
  - 1234567890_2.mp4
  - 1234567890_3.gif

Quoted Tweet: 9876543210 by @other_user
Symlink: 1234567890_quoted_1.link -> ../../../@other_user/9876543210_1.jpg
---
[Optional: Quoted tweet information if present]
Quote Author: @other_user
Quote Posted: 2024-04-04 12:00:00 UTC
Quote Text: [quoted content]
Quote Media: 9876543210_1.jpg (accessible via 1234567890_quoted_1.link)
```

---

## Data Storage & Organization

### Directory Structure

```
~/Documents/X-Bookmarks/
├── @username_1/
│   ├── 1234567890.txt                   # Post content
│   ├── 1234567890_1.jpg                 # First image
│   ├── 1234567890_2.mp4                 # Second media (video)
│   ├── 1234567890_quoted_1.link         # Symlink to quoted post media
│   ├── 1234567891.txt                   # Post with no media
│   ├── 1234567892.txt
│   ├── 1234567892_1.jpg
│   ├── 1234567892_quoted_1.link         # Symlink to its quoted post
│   ├── 1234567892_quoted_2.link         # Multiple quoted media
│   ├── _metadata.json                   # Author statistics
│   └── ...
│
├── @username_2/
│   ├── 9876543210.txt                   # Post content (may be quoted by others)
│   ├── 9876543210_1.jpg
│   ├── 9876543210_2.jpg
│   ├── _metadata.json
│   └── ...
│
└── _processing_summary.json             # Overall statistics
```

### Filename Conventions

- **Post text files:** `{post_id}.txt` (e.g., `1234567890.txt`)
- **Media files:** `{post_id}_{index}.{ext}` (e.g., `1234567890_1.jpg`, `1234567890_2.mp4`)
- **Media index:** 1-indexed, sequential (1, 2, 3...)
- **Quoted post symlinks:** `{parent_id}_quoted_{index}.link` → points to quoted post media
  - Example: `1234567890_quoted_1.link` (first quoted post media)
  - Example: `1234567890_quoted_2.link` (second quoted post media)
- **Metadata:** `_metadata.json` (prefixed with underscore)

### Symlink Structure for Quoted Posts

**Symlink naming for easy grouping by post ID:**
```
@user1/
├── 1234567890.txt                           # Parent post
├── 1234567890_1.jpg                         # Parent media
├── 1234567890_quoted_1.link -> ../../../@user2/9876543210_1.jpg
└── 1234567890_quoted_2.link -> ../../../@user2/9876543210_2.jpg
```

**Benefits of this naming:**
- All files for post `1234567890` group together when sorted
- Quoted media clearly associated with parent post ID
- Easy to see at a glance which posts have quotes
- Sequential indexing (`_quoted_1`, `_quoted_2`) for multiple quoted items

**Alternative with quoted text reference:**
```
@user1/
├── 1234567890.txt                           # Parent post text
├── 1234567890_quoted.link -> ../../../@user2/9876543210.txt
└── 1234567890_quoted_1.link -> ../../../@user2/9876543210_1.jpg
```

**Advantages:**
- Flat file structure - easier to browse
- All content from same author in one directory
- Symlinks maintain relationships between posts
- OS-native shortcuts (work in Finder, CLI)
- No duplication of files
- Easy to understand naming: post_id indicates which post files belong to
- Clear quoted post references via symlink names

---

## State Management

### Database Schema

```sql
-- Main bookmarks tracking
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

-- Individual media files
CREATE TABLE media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    media_type TEXT CHECK(media_type IN ('photo', 'video', 'animated_gif')),
    file_size INT,
    downloaded_at TIMESTAMP,
    FOREIGN KEY (tweet_id) REFERENCES bookmarks(tweet_id)
);

-- Quoted post relationships
CREATE TABLE quoted_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_tweet_id TEXT NOT NULL,
    quoted_tweet_id TEXT NOT NULL,
    symlink_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_tweet_id) REFERENCES bookmarks(tweet_id),
    FOREIGN KEY (quoted_tweet_id) REFERENCES bookmarks(tweet_id)
);

-- Processing history for auditing
CREATE TABLE processing_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    action TEXT CHECK(action IN ('processed', 'skipped', 'failed', 'retried')),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    details TEXT
);
```

### State Manager Methods

```python
class StateManager:
    def mark_processed(
        self,
        tweet_id: str,
        status: str,
        file_paths: List[str],
        media_count: int = 0
    ) -> None:
        """Mark tweet as processed successfully."""
    
    def mark_failed(
        self,
        tweet_id: str,
        error: str,
        retry_count: int = 0
    ) -> None:
        """Mark tweet processing as failed."""
    
    def is_already_processed(self, tweet_id: str) -> bool:
        """Check if tweet was already processed."""
    
    def get_failed_bookmarks(self, limit: int = 100) -> List[Dict]:
        """Retrieve failed processing attempts."""
    
    def get_processing_stats(self) -> ProcessingStats:
        """Get aggregate statistics."""
    
    def clear_old_entries(self, days: int = 90) -> int:
        """Clean up old state records."""
```

---

## Error Handling

### Error Classification

**Category 1: Retriable Errors** (Automatic retry)
- Network timeouts (requests timeout, connection reset)
- Rate limit (HTTP 429)
- Temporary server errors (500, 502, 503)
- Partial media downloads
- **Action:** Retry with exponential backoff (3 attempts, 2s/4s/8s)

**Category 2: Quarantine Errors** (Manual review)
- Content deleted (404 on media URL)
- Access denied (403, 401)
- Invalid URL format
- Corrupted/incomplete file
- Missing required data from API
- **Action:** Move to quarantine, await manual intervention

**Category 3: Skip Errors** (Log & continue)
- Non-critical metadata missing
- Optional media unavailable
- Quote post deleted (process parent only)
- **Action:** Log warning, continue processing

### Quarantine Management

**Quarantine folder structure:**
```
quarantine/
├── failed_items.json          # Index of all failures
├── 2024-04-04/
│   ├── 1234567890.json       # Failed item metadata
│   ├── 1234567891.json
│   └── errors.log            # Error log for the date
└── retry_log.txt             # Retry attempt history
```

**Failed item record:**
```json
{
  "tweet_id": "1234567890",
  "author": "@username",
  "text": "Post content...",
  "failed_at": "2024-04-04T14:30:00Z",
  "error_type": "image_download_timeout",
  "error_message": "Connection timeout after 3 retries",
  "media_items_attempted": 2,
  "media_items_failed": 1,
  "failed_urls": ["https://pbs.twimg.com/..."],
  "retry_count": 2,
  "last_retry": "2024-04-04T14:35:00Z"
}
```

### Recovery Mechanisms

**Automatic recovery:**
- Exponential backoff on network errors (2s, 4s, 8s)
- Resume from last processed bookmark (use state DB)
- Skip already processed items

**Manual recovery:**
```bash
# Retry quarantined items
python -m bookmark_downloader retry_quarantine --limit 10

# Review quarantine status
python -m bookmark_downloader quarantine_status

# Clear quarantine (after manual review)
python -m bookmark_downloader clear_quarantine --older-than 30
```

---

## Scheduling & Deployment

### macOS launchd Configuration

**File:** `schedule/com.user.bookmark-downloader.plist`

**Key settings:**
- **Label:** com.user.bookmark-downloader
- **Program:** Python script path
- **Schedule:** Cron-like with `StartCalendarInterval` array
- **Environment variables:** Via `EnvironmentVariables` dict
- **Logging:** Stdout/stderr to files
- **Run at load:** Auto-start when user logs in (optional)

**Sample Schedule (3x daily):**
- 6:00 AM
- 2:00 PM
- 10:00 PM

### Installation Steps

```bash
# 1. Set up environment
cd X-bookmark-downloader
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure credentials and paths
cp .env.example .env
# Edit .env with X API credentials

# 3. Set up configuration file (choose YAML or JSON)
cp config.example.yaml config.yaml
# OR
cp config.example.json config.json
# Edit with your desired download and log paths

# 4. Verify setup
python -m bookmark_downloader verify_setup

# 5. Test run
python -m bookmark_downloader download --limit 5

# 6. Install scheduler
mkdir -p ~/Library/LaunchAgents
cp schedule/com.user.bookmark-downloader.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.bookmark-downloader.plist

# 7. Verify installation
launchctl list | grep bookmark-downloader
```

### Monitoring

```bash
# View launchd job status
launchctl list | grep bookmark-downloader

# View recent logs
tail -100f logs/bookmark_downloader.log

# Check disk usage
du -sh downloads/

# Check quarantine status
ls -R quarantine/

# Manual run with verbose logging
python -m bookmark_downloader download --log-level DEBUG
```

---

## Testing Strategy

### Unit Tests

**API Client Tests (`test_api.py`):**
- Mock X API responses
- Test bookmark pagination
- Test quote post expansion
- Test media URL extraction
- Test error handling & rate limiting

**Download Tests (`test_download.py`):**
- Mock HTTP responses for images
- Mock yt-dlp for videos
- Test retry logic (success after failures)
- Test timeout handling
- Test filename sanitization

**Storage Tests (`test_storage.py`):**
- Test directory creation
- Test file path generation
- Test metadata file creation
- Test symlink creation
- Test username sanitization

**State Tests (`test_state.py`):**
- Test CRUD operations on database
- Test deduplication logic
- Test state recovery
- Test statistics calculation

### Integration Tests

**Full Flow Tests:**
- Mock API responses + real file system
- Process 5-10 bookmarks start to finish
- Verify directory structure
- Verify database state
- Verify symlinks created

**Error Scenarios:**
- Handle API timeouts
- Handle missing media URLs
- Handle quota deletion (404)
- Handle rate limiting
- Handle disk space errors

### Manual Testing Checklist

- [ ] OAuth authentication successful
- [ ] Fetch 10+ bookmarks with pagination
- [ ] Download images successfully
- [ ] Download videos with yt-dlp
- [ ] Process quoted tweets
- [ ] Create symlinks correctly
- [ ] Deduplication works (skip second run)
- [ ] Error quarantine works
- [ ] Database persists state correctly
- [ ] Directory structure matches spec
- [ ] Metadata files created properly
- [ ] Rate limiting detected correctly
- [ ] launchd schedule works
- [ ] Logs created successfully

---

## Critical Path Dependencies

### Dependency Graph

```
Phase 1: Foundation
  ├─ Phase 2: API Integration
  │   └─ Phase 5: Quote Resolution
  │       └─ Phase 8: Main Orchestrator
  │           └─ Phase 9: Scheduling
  ├─ Phase 3: State Management
  │   └─ Phase 8: Main Orchestrator
  ├─ Phase 4: Media Download
  │   └─ Phase 8: Main Orchestrator
  ├─ Phase 6: Storage
  │   └─ Phase 8: Main Orchestrator
  └─ Phase 7: Error Handling
      └─ Phase 8: Main Orchestrator

Testing (Phase 10): Depends on all phases
```

### Critical Path (Minimum viable execution)

1. Phase 1 (Foundation) - 2-3h
2. Phase 2 (API) - 3-4h
3. Phase 3 (State) - 2-3h
4. Phase 4 (Media) - 4-5h
5. Phase 5 (Quotes) - 2-3h
6. Phase 6 (Storage) - 2-3h
7. Phase 7 (Errors) - 2-3h
8. Phase 8 (Main) - 3-4h
9. Phase 10 (Testing) - 3-4h

**Estimated Total:** 28-36 hours (assuming linear progression with no blockers)

### Prerequisites

**Before Starting:**
1. ✅ X API v2 elevated access (apply at developer.twitter.com)
2. ✅ OAuth credentials (API key, secret, bearer token)
3. ✅ Python 3.9+ installed locally
4. ✅ Basic familiarity with tweepy and yt-dlp

**Critical Blocker:**
- Cannot proceed beyond Phase 2 without X API credentials

---

## Edge Cases & Gaps

### Handled Edge Cases

| Case | Impact | Solution |
|------|--------|----------|
| **Tweet deleted after bookmark** | 404 from API | Quarantine with "deleted" marker |
| **Media URL expires** | 404 during download | Retry with backoff, then quarantine |
| **Rate limit during run** | Processing stops | Detect 429, wait X-RateLimit-Reset, resume |
| **Duplicate bookmarks** | Redundant downloads | Query tweet_id in state DB first |
| **Very large videos** | Disk space issues | Add size check, skip if > threshold |
| **Non-ASCII usernames** | Path encoding errors | URL-encode or sanitize for filesystem |
| **Quoted post deleted** | Cannot fetch quote | Log warning, process parent only |
| **Network interruption** | Partial downloads | Clean up incomplete, retry next run |
| **Disk space exhausted** | Download fails | Monitor free space, alert & stop |
| **Multiple instances running** | Race condition | Check PID lock file before start |
| **Very long post text** | Text file issues | Store properly, handle encoding |
| **Emoji in filenames** | OS errors | Sanitize, use URL encoding or hash |
| **GIF files** | Format handling | Download as mp4 or save directly |

### Known Gaps (Design Decisions Made)

| Gap | Decision | Rationale |
|-----|----------|-----------|
| **Notifications** | Post-MVP feature | Focus on core functionality first |
| **Webhook retry** | Not implemented | Quarantine system sufficient for MVP |
| **Cloud storage** | Local only | Simpler, no dependency |
| **Automatic retry** | Manual via CLI | Avoid unexpected processing |
| **Statistics UI** | Text report only | Can add web UI later |
| **Historical tracking** | Processed items kept in DB | Allows future reconciliation |

### Future Enhancement Opportunities

- Email/Slack notifications with summary
- Web dashboard for statistics
- Quarantine review web interface
- Scheduled automatic retry of failed items
- Support for other bookmark sources (Instagram, TikTok)
- Incremental backups
- Media deduplication across posts
- Advanced search/filtering of downloads
- Integration with media management tools

---

## Configuration Examples

### YAML Configuration (`config.yaml`)

**Minimal Setup (macOS):**
```yaml
twitter:
  bearer_token: ${TWITTER_BEARER_TOKEN}

paths:
  downloads_directory: ~/Documents/X-Bookmarks
  logs_directory: ~/Library/Logs/bookmark-downloader

download:
  video_quality: best
  max_workers: 4

state_management:
  tracking_method: local_logging
```

**Advanced Setup with Custom Paths:**
```yaml
twitter:
  bearer_token: ${TWITTER_BEARER_TOKEN}
  request_timeout: 30

paths:
  # Store downloads in an external drive
  downloads_directory: /Volumes/External-SSD/X-Bookmarks
  # Store logs locally for quick access
  logs_directory: ~/.bookmark-downloader/logs

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
  tracking_method: hybrid  # Can switch to 'local_logging' or 'bookmark_removal'
  retention_days: 90

logging:
  level: DEBUG
  filename: bookmark_downloader.log
  max_bytes: 10485760
  backup_count: 5

quarantine:
  folder: quarantine
```

### JSON Configuration (`config.json`)

**Example with Independent Paths:**
```json
{
  "twitter": {
    "bearer_token": "${TWITTER_BEARER_TOKEN}",
    "request_timeout": 30
  },
  "paths": {
    "downloads_directory": "~/Documents/X-Bookmarks",
    "logs_directory": "~/Library/Logs/bookmark-downloader"
  },
  "download": {
    "image_quality": "high",
    "video_quality": "best",
    "max_workers": 4,
    "timeout_seconds": 600,
    "retry_attempts": 3
  },
  "processing": {
    "follow_quotes": true,
    "max_quote_depth": 1,
    "batch_size": 100
  },
  "state_management": {
    "database_file": "state.db",
    "tracking_method": "local_logging",
    "retention_days": 90
  },
  "logging": {
    "level": "INFO",
    "filename": "bookmark_downloader.log",
    "max_bytes": 10485760,
    "backup_count": 5
  },
  "quarantine": {
    "folder": "quarantine"
  }
}
```

### Environment Variables (`.env`)

**Required:**
```bash
TWITTER_BEARER_TOKEN=your_bearer_token_here
```

**Optional (override config file):**
```bash
# Paths
BOOKMARK_DOWNLOADER_DOWNLOADS_DIR=/path/to/downloads
BOOKMARK_DOWNLOADER_LOGS_DIR=/path/to/logs

# Download settings
BOOKMARK_DOWNLOADER_MAX_WORKERS=4
BOOKMARK_DOWNLOADER_VIDEO_QUALITY=best

# Logging
BOOKMARK_DOWNLOADER_LOG_LEVEL=DEBUG

# State management
BOOKMARK_DOWNLOADER_TRACKING_METHOD=local_logging
```

### Configuration Priority

When multiple config sources are present, they're loaded in this order (later overrides earlier):

1. **Hardcoded defaults** (baseline)
2. **Config file** (`config.yaml` or `config.json`)
3. **Environment variables** (highest priority - override everything)
4. **Command-line arguments** (if implemented)

### Path Expansion Examples

```
Input: ~/Documents/X-Bookmarks
Result: /Users/username/Documents/X-Bookmarks

Input: ./logs
Result: /path/to/config/directory/logs

Input: /Volumes/External/Bookmarks
Result: /Volumes/External/Bookmarks (unchanged)

Input: logs/
Result: ${LOGS_DIRECTORY}/logs
```

### Directory Structure After Configuration

If configured as:
```yaml
paths:
  downloads_directory: ~/Documents/X-Bookmarks
  logs_directory: ~/Library/Logs/bookmark-downloader
```

Resulting structure:
```
~/Documents/X-Bookmarks/
├── @username_1/
├── @username_2/
└── _processing_summary.json

~/Library/Logs/bookmark-downloader/
├── bookmark_downloader.log
├── state.db
└── quarantine/
    ├── failed_items.json
    └── 2024-04-04/
```

---

## Summary & Next Steps

### Immediate Actions

1. **Obtain X API Credentials:**
   - Go to https://developer.twitter.com
   - Apply for elevated access (bookmark endpoints)
   - Create an app and get credentials
   - Document in `.env.example`

2. **Begin Phase 1 Implementation:**
   - Create project structure
   - Set up Python package
   - Implement configuration system
   - Initialize logging

3. **Prepare Development Environment:**
   - Create venv
   - Install base dependencies
   - Set up git branches
   - Create initial commit

### Success Criteria

- ✅ Bookmark fetching from X API
- ✅ All media downloads successfully
- ✅ Proper file organization
- ✅ No reprocessing of duplicates
- ✅ Failed items properly quarantined
- ✅ Scheduling works via launchd
- ✅ Full integration testing passes

### Long-Term Maintenance

- Monitor API changes from X
- Update yt-dlp regularly
- Review quarantine periodically
- Optimize database performance
- Add features based on usage

---

**Plan Version:** 1.0  
**Last Updated:** 2024-04-04  
**Status:** Ready for Implementation
