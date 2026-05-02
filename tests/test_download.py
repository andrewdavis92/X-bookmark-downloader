"""Tests for Phase 4 media download engine."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import httpx
import yt_dlp


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Video downloader tests
# ---------------------------------------------------------------------------


def _yt_dlp_mock(write_bytes=b"fake video data", raise_error=None):
    """Return a mock yt_dlp.YoutubeDL(opts) context manager.

    The mock captures the outtmpl from opts and writes to it on download().
    """
    captured_opts = {}

    def fake_ydl(opts):
        captured_opts.update(opts)

        def fake_download(urls):
            if raise_error:
                raise raise_error
            Path(captured_opts["outtmpl"]).write_bytes(write_bytes)

        mock_ydl = MagicMock()
        mock_ydl.download.side_effect = fake_download
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        return mock_ydl

    return fake_ydl


def test_download_video_success(tmp_path):
    from bookmark_downloader.download.video_downloader import download_video

    dest = tmp_path / "video.mp4"
    with patch("yt_dlp.YoutubeDL", side_effect=_yt_dlp_mock()):
        result = download_video("https://t.co/abc123", dest, "111")

    assert result.success is True
    assert result.file_size == len(b"fake video data")
    assert result.error is None
    assert result.attempts == 1
    assert dest.exists()
    assert not any(p.is_dir() and p.name.startswith("tmp") for p in dest.parent.iterdir())


def test_download_video_download_error(tmp_path):
    from bookmark_downloader.download.video_downloader import download_video

    dest = tmp_path / "video.mp4"
    error = yt_dlp.utils.DownloadError("video unavailable")
    with patch("yt_dlp.YoutubeDL", side_effect=_yt_dlp_mock(raise_error=error)):
        result = download_video("https://t.co/abc123", dest, "111")

    assert result.success is False
    assert result.error is not None
    assert result.file_size == 0


def test_download_video_empty_file(tmp_path):
    from bookmark_downloader.download.video_downloader import download_video

    dest = tmp_path / "video.mp4"
    with patch("yt_dlp.YoutubeDL", side_effect=_yt_dlp_mock(write_bytes=b"")):
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
        return _yt_dlp_mock()(opts)

    with patch("yt_dlp.YoutubeDL", side_effect=capture):
        download_video("https://t.co/abc123", dest, "111")

    assert captured.get("noplaylist") is True
    assert captured.get("quiet") is True
    assert captured.get("no_warnings") is True


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
