# Phase 4: Media Download Engine — Design Spec

**Date:** 2026-05-02  
**Status:** Approved  
**Depends on:** Phase 1 (config), Phase 2 (API client), Phase 3 (state — consumed by orchestrator, not this module)

---

## Goal

Implement the media download engine that takes a list of prepared `MediaItem`s and downloads each to disk, returning detailed per-file results. Covers X-native photos, videos, and animated GIFs only — external platform URLs (YouTube, TikTok, etc.) are out of scope and deferred to a future enhancement.

---

## Scope

**In scope:**
- Download X-native photos via `httpx` streaming
- Download X-native videos and animated GIFs via `yt-dlp`
- Retry logic with exponential backoff (up to 3 attempts)
- Corrupt/incomplete download detection (zero-byte file check)
- Per-file download results aggregated into a stats object
- Sequential downloads (speed is not a concern)

**Out of scope:**
- External platform detection or download (YouTube, TikTok, Instagram, etc.)
- State management — the orchestrator calls `StateManager` based on results
- `MediaItem` construction — done by the orchestrator alongside tweet data gathering
- Concurrent downloads

---

## Architecture

### Option chosen: Thin downloaders, smart coordinator

`image_downloader.py` and `video_downloader.py` are each a single public function — download this URL to this path, return a result. All retry logic, routing, and stats collection live in `media_handler.py`. The downloaders know *how* to fetch; the handler knows *how* to orchestrate.

### Files

| File | Responsibility |
|------|---------------|
| `src/bookmark_downloader/download/image_downloader.py` | Stream a photo URL to disk via `httpx`; validate non-empty |
| `src/bookmark_downloader/download/video_downloader.py` | Download a video/GIF URL via `yt-dlp`; validate non-empty |
| `src/bookmark_downloader/download/media_handler.py` | Data classes, routing, retry loop, stats aggregation |
| `tests/test_download.py` | All download tests (mocked — no real HTTP or yt-dlp) |

No new dependencies — `httpx` and `yt-dlp` are already in `requirements.txt`.

---

## Data Structures

All three dataclasses defined in `media_handler.py` and imported by callers:

```python
@dataclass
class MediaItem:
    url: str
    media_type: str       # "photo", "video", "animated_gif"
    dest_path: Path
    tweet_id: str

@dataclass
class DownloadResult:
    url: str
    dest_path: Path
    success: bool
    file_size: int        # bytes written; 0 if failed
    error: Optional[str]  # None on success, message on failure
    attempts: int         # number of attempts made (1–3)

@dataclass
class DownloadStats:
    tweet_id: str
    total: int
    succeeded: int
    failed: int
    results: List[DownloadResult]  # one per MediaItem, in order
```

`MediaItem`s are constructed by the Phase 8 orchestrator, which has both the tweet data (from `twitter_client.extract_media_urls()`) and the storage paths (from the storage manager). `media_handler` receives fully-populated `MediaItem`s and does not construct them.

---

## `image_downloader.py`

### Public interface

```python
def download_image(url: str, dest_path: Path, tweet_id: str, timeout: int = 60) -> DownloadResult
```

### Behaviour

1. Open an `httpx` streaming GET with the given timeout
2. On non-2xx HTTP status: return `DownloadResult(success=False, error="HTTP {status_code}", attempts=1)`
3. Stream response body to `dest_path.with_suffix('.tmp')` (temp file in same directory)
4. On completion, `rename()` temp file to `dest_path`
5. Check `dest_path.stat().st_size > 0`; if zero, delete the file and return `DownloadResult(success=False, error="empty file", attempts=1)`
6. Return `DownloadResult(success=True, file_size=<bytes>, error=None, attempts=1)`

**Temp-then-rename pattern:** ensures no partial files survive a crash or exception mid-stream. If an exception occurs before rename, the `.tmp` file is cleaned up in a `finally` block.

The function does **not** retry — `media_handler` decides whether to retry.

---

## `video_downloader.py`

### Public interface

```python
def download_video(url: str, dest_path: Path, tweet_id: str, timeout: int = 600) -> DownloadResult
```

Handles both `video` and `animated_gif` media types — animated GIFs on X are served as MP4 files and treated identically to videos.

### Behaviour

1. Configure `yt-dlp` options:
   - `format`: `"bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"` — prefers native mp4, falls back gracefully
   - `outtmpl`: `str(dest_path.with_suffix('.tmp'))` — temp path, renamed on success
   - `noplaylist`: `True` — never expand playlists
   - `socket_timeout`: `timeout`
   - `quiet`: `True`, `no_warnings`: `True` — suppress yt-dlp stdout/stderr
2. Call `yt_dlp.YoutubeDL(opts).download([url])`
3. Rename temp file to `dest_path`
4. Check `dest_path.stat().st_size > 0`; if zero, delete and return failure with `"empty file"`
5. Return `DownloadResult(success=True, file_size=<bytes>, error=None, attempts=1)`

**Error handling:** catch `yt_dlp.utils.DownloadError` and return `DownloadResult(success=False, error=str(e), attempts=1)`. Do not let yt-dlp exceptions propagate — the handler decides what to do with failures.

The function does **not** retry.

---

## `media_handler.py`

### Public interface

```python
def coordinate_downloads(items: List[MediaItem], timeout: int = 600) -> DownloadStats
```

### Routing rule

| `media_type` | Downloader |
|---|---|
| `"photo"` | `download_image` |
| `"video"` | `download_video` |
| `"animated_gif"` | `download_video` |

### Retry loop (per item)

```
max_attempts = 3
backoff = [2, 4, 8]  # seconds between attempts

for attempt in 1..max_attempts:
    result = download_fn(url, dest_path, tweet_id, timeout)
    if result.success:
        record result with attempts=attempt
        break
    if attempt < max_attempts:
        log WARNING "attempt {attempt} failed, retrying in {backoff[attempt-1]}s"
        sleep(backoff[attempt - 1])

if not success after all attempts:
    record result with attempts=max_attempts
```

### Logging

| Event | Level |
|---|---|
| Starting download of item | DEBUG |
| Retry attempt | WARNING |
| Final failure after all attempts | ERROR |
| All items complete | INFO (summary) |

### Return value

Builds and returns `DownloadStats` with counts derived from the collected `DownloadResult` list. The orchestrator inspects `results` to determine what to pass to `StateManager` — e.g. whether a post was fully, partially, or not downloaded.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Non-2xx HTTP response | Return failure result; handler retries |
| Zero-byte file after download | Delete temp/dest file; return failure with "empty file" |
| `yt_dlp.DownloadError` | Caught in `download_video`; return failure result |
| Unknown `media_type` | Log WARNING and skip item; record as failed in stats |
| Exception mid-stream (image) | `finally` block deletes `.tmp` file; exception propagates to handler as failure |

---

## Testing Strategy

All tests in `tests/test_download.py`. No real HTTP calls or real yt-dlp invocations — all mocked at the function boundary.

### Image downloader tests
- Successful download returns `DownloadResult(success=True)` with correct `file_size`
- Non-2xx response returns `DownloadResult(success=False, error="HTTP 404")`
- Zero-byte file returns `DownloadResult(success=False, error="empty file")`
- Timeout exception returns failure result
- Temp file is cleaned up on failure (no `.tmp` left behind)

### Video downloader tests
- Successful download returns `DownloadResult(success=True)`
- `yt_dlp.DownloadError` returns failure result (does not raise)
- Zero-byte file returns failure with "empty file"
- yt-dlp configured with `noplaylist=True` and `quiet=True`

### `coordinate_downloads` tests
- All items succeed → `DownloadStats(succeeded=N, failed=0)`
- Item fails once then succeeds → `attempts=2` in result, backoff sleep called once
- Item fails all 3 attempts → `attempts=3`, counted in `failed`
- `"photo"` routed to `download_image`, `"video"` and `"animated_gif"` routed to `download_video`
- Unknown `media_type` → item skipped, counted as failed
- Returned `DownloadStats.total == len(items)`

---

## Integration Points

**Consumed by:** Phase 8 orchestrator
- Builds `MediaItem` list from `extract_media_urls()` + storage paths
- Calls `coordinate_downloads(items)`
- Inspects `DownloadStats.results` to call `state_manager.mark_processed()` or `mark_failed()`

**Depends on:**
- `httpx` (already in requirements)
- `yt-dlp` (already in requirements)
- `bookmark_downloader.utils.logger` for logging
