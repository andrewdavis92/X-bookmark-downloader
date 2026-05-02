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


def test_is_already_processed_false_for_new_tweet(state_manager):
    assert state_manager.is_already_processed("tweet_1") is False


def test_mark_processed_makes_tweet_processed(state_manager):
    state_manager.mark_processed(
        "tweet_1", "success", ["/downloads/@user/tweet_1_1.jpg"], media_count=1
    )
    assert state_manager.is_already_processed("tweet_1") is True


def test_mark_processed_failed_status_not_processed(state_manager):
    state_manager.mark_processed("tweet_1", "failed", [])
    assert state_manager.is_already_processed("tweet_1") is False


def test_mark_processed_stores_media_count(state_manager):
    state_manager.mark_processed("tweet_1", "success", ["/path/file.jpg"], media_count=3)
    bookmark = state_manager._db._get_bookmark("tweet_1")
    assert bookmark["media_count"] == 3


def test_mark_processed_stores_folder_path(state_manager):
    state_manager.mark_processed(
        "tweet_1", "success", ["/downloads/@user/tweet_1_1.jpg"]
    )
    bookmark = state_manager._db._get_bookmark("tweet_1")
    assert bookmark["folder_path"] == "/downloads/@user/tweet_1_1.jpg"


def test_mark_processed_with_empty_file_paths(state_manager):
    state_manager.mark_processed("tweet_1", "success", [])
    assert state_manager.is_already_processed("tweet_1") is True


def test_mark_processed_logs_history(state_manager):
    state_manager.mark_processed("tweet_1", "success", [], media_count=2)
    cursor = state_manager._db._conn.execute(
        "SELECT action FROM processing_history WHERE tweet_id = 'tweet_1'"
    )
    assert cursor.fetchone()["action"] == "processed"


def test_mark_failed_sets_status(state_manager):
    state_manager.mark_failed("tweet_2", "Download timed out")
    bookmark = state_manager._db._get_bookmark("tweet_2")
    assert bookmark["status"] == "failed"
    assert bookmark["last_error"] == "Download timed out"


def test_mark_failed_not_counted_as_processed(state_manager):
    state_manager.mark_failed("tweet_2", "some error")
    assert state_manager.is_already_processed("tweet_2") is False


def test_mark_failed_stores_retry_count(state_manager):
    state_manager.mark_failed("tweet_2", "error", retry_count=2)
    bookmark = state_manager._db._get_bookmark("tweet_2")
    assert bookmark["retry_count"] == 2


def test_mark_failed_logs_history(state_manager):
    state_manager.mark_failed("tweet_2", "network error")
    cursor = state_manager._db._conn.execute(
        "SELECT action, details FROM processing_history WHERE tweet_id = 'tweet_2'"
    )
    row = cursor.fetchone()
    assert row["action"] == "failed"
    assert row["details"] == "network error"


def test_update_status_changes_status(state_manager):
    state_manager.mark_failed("tweet_3", "temp error")
    state_manager.update_status("tweet_3", "success")
    bookmark = state_manager._db._get_bookmark("tweet_3")
    assert bookmark["status"] == "success"


def test_update_status_sets_error_message(state_manager):
    state_manager.update_status("tweet_4", "failed", error="403 Forbidden")
    bookmark = state_manager._db._get_bookmark("tweet_4")
    assert bookmark["last_error"] == "403 Forbidden"


def test_update_status_on_new_tweet(state_manager):
    state_manager.update_status("tweet_5", "quarantined", error="missing media")
    bookmark = state_manager._db._get_bookmark("tweet_5")
    assert bookmark["status"] == "quarantined"


def test_update_status_without_error(state_manager):
    state_manager.update_status("tweet_6", "success")
    bookmark = state_manager._db._get_bookmark("tweet_6")
    assert bookmark["status"] == "success"
    assert bookmark["last_error"] is None


def test_get_failed_bookmarks_returns_failed(state_manager):
    state_manager.mark_failed("tweet_a", "err1")
    state_manager.mark_failed("tweet_b", "err2")
    state_manager.mark_processed("tweet_c", "success", [])
    results = state_manager.get_failed_bookmarks()
    ids = {r["tweet_id"] for r in results}
    assert "tweet_a" in ids
    assert "tweet_b" in ids
    assert "tweet_c" not in ids


def test_get_failed_bookmarks_respects_limit(state_manager):
    for i in range(5):
        state_manager.mark_failed(f"tweet_{i}", "error")
    results = state_manager.get_failed_bookmarks(limit=3)
    assert len(results) == 3


def test_get_failed_bookmarks_empty_when_none(state_manager):
    assert state_manager.get_failed_bookmarks() == []


def test_get_failed_bookmarks_returns_dicts(state_manager):
    state_manager.mark_failed("tweet_z", "something broke")
    results = state_manager.get_failed_bookmarks()
    assert isinstance(results[0], dict)
    assert "tweet_id" in results[0]
    assert "last_error" in results[0]
