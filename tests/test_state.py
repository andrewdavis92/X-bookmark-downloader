"""Tests for state management (Phase 3)."""

from bookmark_downloader.storage.database import ProcessingStats, SCHEMA_VERSION


def test_processing_stats_fields():
    stats = ProcessingStats(
        total_processed=10,
        total_failed=2,
        total_quarantined=1,
        total_media_downloaded=20,
        last_run_at="2026-05-02T12:00:00",
    )
    assert stats.total_processed == 10
    assert stats.total_failed == 2
    assert stats.total_quarantined == 1
    assert stats.total_media_downloaded == 20
    assert stats.last_run_at == "2026-05-02T12:00:00"


def test_processing_stats_optional_last_run():
    stats = ProcessingStats(
        total_processed=0,
        total_failed=0,
        total_quarantined=0,
        total_media_downloaded=0,
        last_run_at=None,
    )
    assert stats.last_run_at is None


def test_schema_version_is_int():
    assert isinstance(SCHEMA_VERSION, int)
    assert SCHEMA_VERSION >= 1
