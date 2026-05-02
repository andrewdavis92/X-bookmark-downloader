"""Tests for state management (Phase 3)."""

from bookmark_downloader.storage.database import ProcessingStats, SCHEMA_VERSION, Database


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


def test_database_creates_file(db_path, db):
    assert db_path.exists()


def test_database_creates_all_tables(db):
    cursor = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cursor.fetchall()}
    # sqlite_sequence is automatically created by SQLite for AUTOINCREMENT tables
    tables.discard("sqlite_sequence")
    assert tables == {
        "bookmarks",
        "media_files",
        "processing_history",
        "quoted_posts",
        "schema_version",
    }


def test_database_schema_version(db):
    cursor = db._conn.execute("SELECT version FROM schema_version")
    assert cursor.fetchone()[0] == SCHEMA_VERSION


def test_database_reopen_is_idempotent(db_path, db):
    db2 = Database(db_path)
    cursor = db2._conn.execute("SELECT version FROM schema_version")
    assert cursor.fetchone()[0] == SCHEMA_VERSION
    db2.close()
