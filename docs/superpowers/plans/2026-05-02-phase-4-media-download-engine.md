# Phase 4: Media Download Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the media download engine — httpx streaming for photos, yt-dlp for videos and animated GIFs, with a retry-aware coordinator that aggregates per-file results into a stats object.

**Architecture:** Three focused modules — `image_downloader.py` and `video_downloader.py` each expose one public function with no retry logic; `media_handler.py` defines all three dataclasses and `coordinate_downloads()`, which handles routing, exponential-backoff retries, and stats. All tests live in a single `tests/test_download.py` file, mocked at the function boundary with no real HTTP calls or yt-dlp invocations.

**Tech Stack:** Python stdlib (`dataclasses`, `pathlib`, `time`, `logging`), `httpx` (streaming GET), `yt-dlp` (video/GIF download) — both already in `requirements.txt`.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `src/bookmark_downloader/download/media_handler.py` | `MediaItem`, `DownloadResult`, `DownloadStats` dataclasses; `coordinate_downloads()` |
| Create | `src/bookmark_downloader/download/image_downloader.py` | `download_image()` — httpx streaming GET, temp-then-rename |
| Create | `src/bookmark_downloader/download/video_downloader.py` | `download_video()` — yt-dlp download, temp-then-rename |
| Create | `tests/test_download.py` | All Phase 4 tests |

`src/bookmark_downloader/download/__init__.py` already exists (empty) — do not modify it.

---

## Task 1: Dataclasses scaffold in media_handler.py

**Files:**
- Create: `src/bookmark_downloader/download/media_handler.py`
- Create: `tests/test_download.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_download.py
"""Tests for Phase 4 media download engine."""

from pathlib import Path


def test_media_item_fields():
    from bookmark_downloader.download.media_handler import MediaItem

    item = MediaItem(
        url="https://pbs.twimg.com/media/abc.jpg",
        media_type="photo",
        dest_path=Path("/tmp/abc.jpg"),
        tweet_id="111222333",
    )
    assert item.url == "https://pbs.twimg.com/media/abc.jpg"
    assert item.media_type == "photo"
    assert item.dest_path == Path("/tmp/abc.jpg")
    assert item.tweet_id == "111222333"


def test_download_result_success_fields():
    from bookmark_downloader.download.media_handler import DownloadResult

    result = DownloadResult(
        url="https://pbs.twimg.com/media/abc.jpg",
        dest_path=Path("/tmp/abc.jpg"),
        success=True,
        file_size=1024,
        error=None,
        attempts=1,
    )
    assert result.success is True
    assert result.file_size == 1024
    assert result.error is None
    assert result.attempts == 1


def test_download_result_failure_fields():
    from bookmark_downloader.download.media_handler import DownloadResult

    result = DownloadResult(
        url="https://pbs.twimg.com/media/abc.jpg",
        dest_path=Path("/tmp/abc.jpg"),
        success=False,
        file_size=0,
        error="HTTP 404",
        attempts=1,
    )
    assert result.success is False
    assert result.file_size == 0
    assert result.error == "HTTP 404"


def test_download_stats_fields():
    from bookmark_downloader.download.media_handler import DownloadResult, DownloadStats

    r = DownloadResult(
        url="https://pbs.twimg.com/media/abc.jpg",
        dest_path=Path("/tmp/abc.jpg"),
        success=True,
        file_size=512,
        error=None,
        attempts=1,
    )
    stats = DownloadStats(
        tweet_id="111222333",
        total=1,
        succeeded=1,
        failed=0,
        results=[r],
    )
    assert stats.tweet_id == "111222333"
    assert stats.total == 1
    assert stats.succeeded == 1
    assert stats.failed == 0
    assert len(stats.results) == 1
    assert stats.results[0] is r
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_download.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'bookmark_downloader.download.media_handler'`

- [ ] **Step 3: Create media_handler.py with dataclasses**

```python
# src/bookmark_downloader/download/media_handler.py
"""Media download coordinator for X bookmark downloader."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class MediaItem:
    url: str
    media_type: str
    dest_path: Path
    tweet_id: str


@dataclass
class DownloadResult:
    url: str
    dest_path: Path
    success: bool
    file_size: int
    error: Optional[str]
    attempts: int


@dataclass
class DownloadStats:
    tweet_id: str
    total: int
    succeeded: int
    failed: int
    results: List[DownloadResult]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_download.py -v
```
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/bookmark_downloader/download/media_handler.py tests/test_download.py
git commit -m "feat(download): add MediaItem, DownloadResult, DownloadStats dataclasses"
```

---

## Task 2: image_downloader.py

**Files:**
- Create: `src/bookmark_downloader/download/image_downloader.py`
- Modify: `tests/test_download.py` (append tests below the Task 1 tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_download.py` (add the two new imports at the top of the file alongside the existing `from pathlib import Path`):

```python
# Add to top-of-file imports:
# from unittest.mock import MagicMock, patch
# import httpx
```

Then append these test functions:

```python
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch
import httpx


def _httpx_mock(status_code, chunks):
    """Return a mock httpx.stream() context manager."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.iter_bytes.return_value = iter(chunks)
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_response
    mock_cm.__exit__.return_value = False
    return mock_cm


# ---------------------------------------------------------------------------
# Image downloader tests
# ---------------------------------------------------------------------------


def test_download_image_success(tmp_path):
    from bookmark_downloader.download.image_downloader import download_image

    dest = tmp_path / "photo.jpg"
    with patch("httpx.stream", return_value=_httpx_mock(200, [b"fake image data"])):
        result = download_image("https://pbs.twimg.com/media/abc.jpg", dest, "111")

    assert result.success is True
    assert result.file_size == len(b"fake image data")
    assert result.error is None
    assert result.attempts == 1
    assert dest.exists()
    assert not dest.with_suffix(".tmp").exists()


def test_download_image_non_2xx(tmp_path):
    from bookmark_downloader.download.image_downloader import download_image

    dest = tmp_path / "photo.jpg"
    with patch("httpx.stream", return_value=_httpx_mock(404, [])):
        result = download_image("https://pbs.twimg.com/media/abc.jpg", dest, "111")

    assert result.success is False
    assert result.error == "HTTP 404"
    assert result.file_size == 0
    assert not dest.exists()


def test_download_image_empty_file(tmp_path):
    from bookmark_downloader.download.image_downloader import download_image

    dest = tmp_path / "photo.jpg"
    # iter_bytes yields nothing → 0-byte temp file
    with patch("httpx.stream", return_value=_httpx_mock(200, [])):
        result = download_image("https://pbs.twimg.com/media/abc.jpg", dest, "111")

    assert result.success is False
    assert result.error == "empty file"
    assert not dest.exists()


def test_download_image_timeout_returns_failure(tmp_path):
    from bookmark_downloader.download.image_downloader import download_image

    dest = tmp_path / "photo.jpg"
    with patch("httpx.stream", side_effect=httpx.TimeoutException("timed out")):
        result = download_image("https://pbs.twimg.com/media/abc.jpg", dest, "111")

    assert result.success is False
    assert result.file_size == 0
    assert result.error is not None


def test_download_image_no_tmp_left_on_exception(tmp_path):
    from bookmark_downloader.download.image_downloader import download_image

    dest = tmp_path / "photo.jpg"
    # Simulate exception mid-stream (after the temp file is opened)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.iter_bytes.side_effect = IOError("connection reset")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_response
    mock_cm.__exit__.return_value = False

    with patch("httpx.stream", return_value=mock_cm):
        result = download_image("https://pbs.twimg.com/media/abc.jpg", dest, "111")

    assert result.success is False
    assert not dest.with_suffix(".tmp").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_download.py -k "image" -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'bookmark_downloader.download.image_downloader'`

- [ ] **Step 3: Create image_downloader.py**

```python
# src/bookmark_downloader/download/image_downloader.py
"""HTTP image downloader for X-native photos."""

from pathlib import Path

import httpx

from bookmark_downloader.download.media_handler import DownloadResult


def download_image(url: str, dest_path: Path, tweet_id: str, timeout: int = 60) -> DownloadResult:
    tmp_path = dest_path.with_suffix(".tmp")
    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
            if not (200 <= response.status_code < 300):
                return DownloadResult(
                    url=url,
                    dest_path=dest_path,
                    success=False,
                    file_size=0,
                    error=f"HTTP {response.status_code}",
                    attempts=1,
                )
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        tmp_path.rename(dest_path)
        file_size = dest_path.stat().st_size
        if file_size == 0:
            dest_path.unlink()
            return DownloadResult(
                url=url,
                dest_path=dest_path,
                success=False,
                file_size=0,
                error="empty file",
                attempts=1,
            )
        return DownloadResult(
            url=url,
            dest_path=dest_path,
            success=True,
            file_size=file_size,
            error=None,
            attempts=1,
        )
    except Exception as e:
        return DownloadResult(
            url=url,
            dest_path=dest_path,
            success=False,
            file_size=0,
            error=str(e),
            attempts=1,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
```

**How the temp-then-rename pattern works:**
- `open(tmp_path, "wb")` creates a `.tmp` sibling of the destination.
- On success the file is renamed atomically to `dest_path` — no partial file can survive a mid-stream crash.
- The `finally` block deletes `.tmp` if it still exists (covers all failure paths before the rename).
- After a successful rename `tmp_path` is gone, so `finally` is a no-op.

- [ ] **Step 4: Run image tests to verify they pass**

```bash
pytest tests/test_download.py -k "image" -v
```
Expected: 5 tests PASS

- [ ] **Step 5: Run full test suite for regressions**

```bash
pytest -v
```
Expected: All previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/bookmark_downloader/download/image_downloader.py tests/test_download.py
git commit -m "feat(download): add image_downloader with httpx streaming and temp-rename pattern"
```

---

## Task 3: video_downloader.py

**Files:**
- Create: `src/bookmark_downloader/download/video_downloader.py`
- Modify: `tests/test_download.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Add `import yt_dlp` near the top of `tests/test_download.py` (with the other imports). Then append:

```python
# ---------------------------------------------------------------------------
# Video downloader tests
# ---------------------------------------------------------------------------


def _yt_dlp_mock(dest, write_bytes=b"fake video data", raise_error=None):
    """Return a mock yt_dlp.YoutubeDL(opts) context manager."""
    def fake_download(urls):
        if raise_error:
            raise raise_error
        dest.with_suffix(".tmp").write_bytes(write_bytes)

    mock_ydl = MagicMock()
    mock_ydl.download.side_effect = fake_download
    mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
    mock_ydl.__exit__ = MagicMock(return_value=False)
    return mock_ydl


def test_download_video_success(tmp_path):
    from bookmark_downloader.download.video_downloader import download_video

    dest = tmp_path / "video.mp4"
    with patch("yt_dlp.YoutubeDL", return_value=_yt_dlp_mock(dest)):
        result = download_video("https://t.co/abc123", dest, "111")

    assert result.success is True
    assert result.file_size == len(b"fake video data")
    assert result.error is None
    assert result.attempts == 1
    assert dest.exists()
    assert not dest.with_suffix(".tmp").exists()


def test_download_video_download_error(tmp_path):
    from bookmark_downloader.download.video_downloader import download_video

    dest = tmp_path / "video.mp4"
    error = yt_dlp.utils.DownloadError("video unavailable")
    with patch("yt_dlp.YoutubeDL", return_value=_yt_dlp_mock(dest, raise_error=error)):
        result = download_video("https://t.co/abc123", dest, "111")

    assert result.success is False
    assert result.error is not None
    assert result.file_size == 0


def test_download_video_empty_file(tmp_path):
    from bookmark_downloader.download.video_downloader import download_video

    dest = tmp_path / "video.mp4"
    with patch("yt_dlp.YoutubeDL", return_value=_yt_dlp_mock(dest, write_bytes=b"")):
        result = download_video("https://t.co/abc123", dest, "111")

    assert result.success is False
    assert result.error == "empty file"
    assert not dest.exists()


def test_download_video_yt_dlp_options(tmp_path):
    from bookmark_downloader.download.video_downloader import download_video

    dest = tmp_path / "video.mp4"
    captured = {}

    def capture(opts):
        captured.update(opts)
        return _yt_dlp_mock(dest)

    with patch("yt_dlp.YoutubeDL", side_effect=capture):
        download_video("https://t.co/abc123", dest, "111")

    assert captured.get("noplaylist") is True
    assert captured.get("quiet") is True
    assert captured.get("no_warnings") is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_download.py -k "video" -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'bookmark_downloader.download.video_downloader'`

- [ ] **Step 3: Create video_downloader.py**

```python
# src/bookmark_downloader/download/video_downloader.py
"""yt-dlp video and animated GIF downloader for X-native media."""

from pathlib import Path

import yt_dlp

from bookmark_downloader.download.media_handler import DownloadResult


def download_video(url: str, dest_path: Path, tweet_id: str, timeout: int = 600) -> DownloadResult:
    tmp_path = dest_path.with_suffix(".tmp")
    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(tmp_path),
        "noplaylist": True,
        "socket_timeout": timeout,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        tmp_path.rename(dest_path)
        file_size = dest_path.stat().st_size
        if file_size == 0:
            dest_path.unlink()
            return DownloadResult(
                url=url,
                dest_path=dest_path,
                success=False,
                file_size=0,
                error="empty file",
                attempts=1,
            )
        return DownloadResult(
            url=url,
            dest_path=dest_path,
            success=True,
            file_size=file_size,
            error=None,
            attempts=1,
        )
    except yt_dlp.utils.DownloadError as e:
        return DownloadResult(
            url=url,
            dest_path=dest_path,
            success=False,
            file_size=0,
            error=str(e),
            attempts=1,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
```

**`animated_gif` note:** X serves animated GIFs as MP4 files. `download_video` handles both `video` and `animated_gif` media types — the coordinator routes both to this function.

- [ ] **Step 4: Run video tests to verify they pass**

```bash
pytest tests/test_download.py -k "video" -v
```
Expected: 4 tests PASS

- [ ] **Step 5: Run full test suite for regressions**

```bash
pytest -v
```
Expected: All previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/bookmark_downloader/download/video_downloader.py tests/test_download.py
git commit -m "feat(download): add video_downloader with yt-dlp and temp-rename pattern"
```

---

## Task 4: coordinate_downloads in media_handler.py

**Files:**
- Modify: `src/bookmark_downloader/download/media_handler.py` (replace with complete final version below)
- Modify: `tests/test_download.py` (append tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_download.py`:

```python
# ---------------------------------------------------------------------------
# coordinate_downloads tests
# ---------------------------------------------------------------------------


def _make_items(tmp_path, specs):
    """Build MediaItems from (media_type, filename) pairs, all for tweet 111222333."""
    from bookmark_downloader.download.media_handler import MediaItem
    return [
        MediaItem(
            url=f"https://example.com/{fname}",
            media_type=mtype,
            dest_path=tmp_path / fname,
            tweet_id="111222333",
        )
        for mtype, fname in specs
    ]


def _ok(item):
    from bookmark_downloader.download.media_handler import DownloadResult
    return DownloadResult(
        url=item.url, dest_path=item.dest_path,
        success=True, file_size=100, error=None, attempts=1,
    )


def _fail(item):
    from bookmark_downloader.download.media_handler import DownloadResult
    return DownloadResult(
        url=item.url, dest_path=item.dest_path,
        success=False, file_size=0, error="network error", attempts=1,
    )


def test_coordinate_all_succeed(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [("photo", "a.jpg"), ("video", "b.mp4")])

    with patch("bookmark_downloader.download.media_handler.download_image") as mock_img, \
         patch("bookmark_downloader.download.media_handler.download_video") as mock_vid:
        mock_img.return_value = _ok(items[0])
        mock_vid.return_value = _ok(items[1])
        stats = coordinate_downloads(items)

    assert stats.succeeded == 2
    assert stats.failed == 0
    assert stats.total == 2
    assert len(stats.results) == 2


def test_coordinate_retry_then_succeed(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [("photo", "a.jpg")])

    with patch("bookmark_downloader.download.media_handler.download_image") as mock_img, \
         patch("bookmark_downloader.download.media_handler.time") as mock_time:
        mock_img.side_effect = [_fail(items[0]), _ok(items[0])]
        stats = coordinate_downloads(items)

    assert stats.succeeded == 1
    assert stats.failed == 0
    assert stats.results[0].attempts == 2
    mock_time.sleep.assert_called_once_with(2)


def test_coordinate_all_attempts_fail(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [("photo", "a.jpg")])

    with patch("bookmark_downloader.download.media_handler.download_image") as mock_img, \
         patch("bookmark_downloader.download.media_handler.time"):
        mock_img.return_value = _fail(items[0])
        stats = coordinate_downloads(items)

    assert stats.succeeded == 0
    assert stats.failed == 1
    assert stats.results[0].attempts == 3


def test_coordinate_photo_routes_to_image(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [("photo", "a.jpg")])

    with patch("bookmark_downloader.download.media_handler.download_image") as mock_img, \
         patch("bookmark_downloader.download.media_handler.download_video") as mock_vid:
        mock_img.return_value = _ok(items[0])
        coordinate_downloads(items)

    mock_img.assert_called_once()
    mock_vid.assert_not_called()


def test_coordinate_video_routes_to_video(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [("video", "b.mp4")])

    with patch("bookmark_downloader.download.media_handler.download_image") as mock_img, \
         patch("bookmark_downloader.download.media_handler.download_video") as mock_vid:
        mock_vid.return_value = _ok(items[0])
        coordinate_downloads(items)

    mock_vid.assert_called_once()
    mock_img.assert_not_called()


def test_coordinate_animated_gif_routes_to_video(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [("animated_gif", "c.mp4")])

    with patch("bookmark_downloader.download.media_handler.download_image") as mock_img, \
         patch("bookmark_downloader.download.media_handler.download_video") as mock_vid:
        mock_vid.return_value = _ok(items[0])
        coordinate_downloads(items)

    mock_vid.assert_called_once()
    mock_img.assert_not_called()


def test_coordinate_unknown_type_counted_as_failed(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [("external_link", "x.html")])
    stats = coordinate_downloads(items)

    assert stats.failed == 1
    assert stats.succeeded == 0
    assert stats.results[0].success is False


def test_coordinate_total_equals_len_items(tmp_path):
    from bookmark_downloader.download.media_handler import coordinate_downloads

    items = _make_items(tmp_path, [
        ("photo", "a.jpg"),
        ("video", "b.mp4"),
        ("animated_gif", "c.mp4"),
    ])

    with patch("bookmark_downloader.download.media_handler.download_image") as mock_img, \
         patch("bookmark_downloader.download.media_handler.download_video") as mock_vid:
        mock_img.return_value = _ok(items[0])
        mock_vid.side_effect = [_ok(items[1]), _ok(items[2])]
        stats = coordinate_downloads(items)

    assert stats.total == 3
    assert stats.tweet_id == "111222333"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_download.py -k "coordinate" -v
```
Expected: FAIL with `ImportError: cannot import name 'coordinate_downloads' from 'bookmark_downloader.download.media_handler'`

- [ ] **Step 3: Replace media_handler.py with its complete final form**

```python
# src/bookmark_downloader/download/media_handler.py
"""Media download coordinator for X bookmark downloader."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from bookmark_downloader.download.image_downloader import download_image
from bookmark_downloader.download.video_downloader import download_video
from bookmark_downloader.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MediaItem:
    url: str
    media_type: str
    dest_path: Path
    tweet_id: str


@dataclass
class DownloadResult:
    url: str
    dest_path: Path
    success: bool
    file_size: int
    error: Optional[str]
    attempts: int


@dataclass
class DownloadStats:
    tweet_id: str
    total: int
    succeeded: int
    failed: int
    results: List[DownloadResult]


def coordinate_downloads(items: List[MediaItem], timeout: int = 600) -> DownloadStats:
    results: List[DownloadResult] = []
    max_attempts = 3
    backoff = [2, 4, 8]

    for item in items:
        logger.debug("Downloading %s for tweet %s", item.url, item.tweet_id)

        if item.media_type == "photo":
            download_fn = download_image
        elif item.media_type in ("video", "animated_gif"):
            download_fn = download_video
        else:
            logger.warning(
                "Unknown media_type '%s' for tweet %s, skipping",
                item.media_type,
                item.tweet_id,
            )
            results.append(DownloadResult(
                url=item.url,
                dest_path=item.dest_path,
                success=False,
                file_size=0,
                error=f"unknown media_type: {item.media_type}",
                attempts=0,
            ))
            continue

        result = None
        for attempt in range(1, max_attempts + 1):
            result = download_fn(item.url, item.dest_path, item.tweet_id, timeout)
            result.attempts = attempt
            if result.success:
                break
            if attempt < max_attempts:
                logger.warning(
                    "Attempt %d failed for %s: %s, retrying in %ds",
                    attempt,
                    item.url,
                    result.error,
                    backoff[attempt - 1],
                )
                time.sleep(backoff[attempt - 1])

        if not result.success:
            logger.error(
                "All %d attempts failed for %s: %s",
                max_attempts,
                item.url,
                result.error,
            )

        results.append(result)

    succeeded = sum(1 for r in results if r.success)
    tweet_id = items[0].tweet_id if items else ""

    logger.info(
        "Downloads complete for tweet %s: %d/%d succeeded",
        tweet_id,
        succeeded,
        len(items),
    )
    return DownloadStats(
        tweet_id=tweet_id,
        total=len(items),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )
```

**Patching note for tests:** `download_image` and `download_video` are imported into `media_handler`'s namespace, so tests patch them as `bookmark_downloader.download.media_handler.download_image` (not at their source modules). `time` is patched the same way to suppress real sleeps.

- [ ] **Step 4: Run coordinator tests to verify they pass**

```bash
pytest tests/test_download.py -k "coordinate" -v
```
Expected: 8 tests PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```
Expected: All tests pass (including all Phase 1–3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/bookmark_downloader/download/media_handler.py tests/test_download.py
git commit -m "feat(download): add coordinate_downloads with routing, retry backoff, and stats"
```
