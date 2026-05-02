"""Tests for state management (Phase 3)."""

from bookmark_downloader.storage.database import ProcessingStats, SCHEMA_VERSION, Database, StateManager


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


def test_bookmark_exists_false_for_unknown(db):
    assert db._bookmark_exists("no_such_id") is False


def test_upsert_bookmark_creates_record(db):
    db._upsert_bookmark("tweet_1", status="success")
    assert db._bookmark_exists("tweet_1") is True


def test_get_bookmark_returns_record(db):
    db._upsert_bookmark("tweet_1", status="success", author_username="@alice")
    result = db._get_bookmark("tweet_1")
    assert result is not None
    assert result["tweet_id"] == "tweet_1"
    assert result["status"] == "success"
    assert result["author_username"] == "@alice"


def test_get_bookmark_returns_none_for_missing(db):
    assert db._get_bookmark("no_such_tweet") is None


def test_upsert_updates_existing_record(db):
    db._upsert_bookmark("tweet_1", status="failed")
    db._upsert_bookmark("tweet_1", status="success")
    result = db._get_bookmark("tweet_1")
    assert result["status"] == "success"


def test_upsert_does_not_duplicate(db):
    db._upsert_bookmark("tweet_1", status="failed")
    db._upsert_bookmark("tweet_1", status="success")
    cursor = db._conn.execute(
        "SELECT COUNT(*) FROM bookmarks WHERE tweet_id = 'tweet_1'"
    )
    assert cursor.fetchone()[0] == 1


def test_log_history_inserts_row(db):
    db._upsert_bookmark("tweet_1", status="success")
    db._log_history("tweet_1", "processed", "media_count=3")
    cursor = db._conn.execute(
        "SELECT action, details FROM processing_history WHERE tweet_id = 'tweet_1'"
    )
    row = cursor.fetchone()
    assert row["action"] == "processed"
    assert row["details"] == "media_count=3"


def test_log_history_without_details(db):
    db._upsert_bookmark("tweet_1", status="failed")
    db._log_history("tweet_1", "failed")
    cursor = db._conn.execute(
        "SELECT action FROM processing_history WHERE tweet_id = 'tweet_1'"
    )
    assert cursor.fetchone()["action"] == "failed"


def test_log_history_multiple_entries(db):
    db._upsert_bookmark("tweet_1", status="failed")
    db._log_history("tweet_1", "failed", "attempt 1")
    db._log_history("tweet_1", "retried", "attempt 2")
    cursor = db._conn.execute(
        "SELECT COUNT(*) FROM processing_history WHERE tweet_id = 'tweet_1'"
    )
    assert cursor.fetchone()[0] == 2


def test_state_manager_constructs(state_manager):
    assert state_manager is not None


def test_state_manager_creates_db_file(db_path, state_manager):
    assert db_path.exists()


def test_state_manager_close_is_safe(state_manager):
    state_manager.close()  # should not raise
