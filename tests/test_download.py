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
