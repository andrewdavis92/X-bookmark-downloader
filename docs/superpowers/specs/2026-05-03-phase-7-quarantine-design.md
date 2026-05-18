# Phase 7: Error Handling & Quarantine System — Design Spec

**Date:** 2026-05-03
**Status:** Approved
**Depends on:** Phase 1 (config), Phase 3 (state management), Phase 6 (local storage)

---

## Goal

Implement `storage/quarantine.py` — error classification and quarantine management for failed bookmark processing. Extend `StateManager` with quarantine-aware DB methods. Fill in the `retry_quarantine` stub in `main.py`.

---

## Scope

**In scope:**
- `storage/quarantine.py` — `ErrorCategory` enum, `classify_error()`, `QuarantineManager`
- `storage/database.py` — add `mark_quarantined()` and `get_quarantined_bookmarks()` to `StateManager`
- `main.py` — fill in `retry_quarantine()` stub
- `tests/test_quarantine.py` — 14 tests
- `tests/test_state.py` — 4 new tests for the two new `StateManager` methods

**Out of scope:**
- The Phase 8 orchestrator that calls `quarantine_item` during normal processing
- `_reprocess_tweet()` implementation (Phase 8 fills this in)
- `_processing_summary.json` (Phase 8)

---

## Architecture

### Design decision: Option A — `QuarantineManager` + thin `StateManager` extensions

`QuarantineManager` depends only on `Config` (no `StateManager` coupling), mirroring how `LocalStorage` and `StateManager` split responsibilities for successful downloads. `retry_quarantine` in `main.py` is the only place that coordinates both managers.

### Files

| File | Change |
|------|--------|
| `src/bookmark_downloader/storage/quarantine.py` | New — `ErrorCategory`, `classify_error`, `QuarantineManager` |
| `src/bookmark_downloader/storage/database.py` | Modify — add `mark_quarantined()`, `get_quarantined_bookmarks()` to `StateManager` |
| `src/bookmark_downloader/main.py` | Modify — fill in `retry_quarantine()` |
| `tests/test_quarantine.py` | New — 14 quarantine tests |
| `tests/test_state.py` | Modify — 4 new StateManager tests |

No other files change.

---

## Error Classification

### `ErrorCategory` enum

```python
class ErrorCategory(Enum):
    RETRIABLE = "retriable"   # transient — retry with backoff
    PERMANENT = "permanent"   # unrecoverable — manual review
    SKIP      = "skip"        # non-essential — log and continue (orchestrator only)
```

`SKIP` is never returned by `classify_error` — it is reserved for the Phase 8 orchestrator to use when non-essential metadata is absent before any exception is raised.

### `classify_error(exc: Exception) -> ErrorCategory`

Pure function, no I/O.

| Exception | Category |
|-----------|----------|
| `RateLimitError` | `RETRIABLE` |
| `TimeoutError`, `ConnectionError` | `RETRIABLE` |
| `ValueError` with message containing "500" or "503" | `RETRIABLE` |
| `ValueError` with message containing "404" or "403" | `PERMANENT` |
| `ValueError` (all other) | `PERMANENT` |
| `PermissionError` | `PERMANENT` |
| `OSError` | `PERMANENT` |
| Any other exception | `PERMANENT` (safe default) |

---

## `storage/quarantine.py`

### Public interface

```python
class QuarantineManager:
    def __init__(self, config: Config) -> None

    # Path helper — no I/O
    def get_item_dir(self, tweet_id: str) -> Path

    # Side-effect operations
    def quarantine_item(
        self,
        tweet_id: str,
        tweet_data: Optional[Dict],
        error: Exception,
        error_category: ErrorCategory,
        retry_count: int = 0,
    ) -> Path

    def get_tweet_data(self, tweet_id: str) -> Optional[Dict]
    def remove_item(self, tweet_id: str) -> None
    def list_quarantined_ids(self) -> List[str]
    def generate_report(self, results: List[Dict]) -> Path
```

### Directory structure

```
{quarantine_dir}/
├── 1234567890/
│   ├── tweet.json      # raw TweetData dict — absent if tweet_data=None
│   └── error.txt       # human-readable error details
└── quarantine_report_20260503_143000.txt   # written by generate_report
```

### `error.txt` format

```
Tweet ID:    1234567890
Quarantined: 2026-05-03T14:30:00
Category:    permanent
Error Type:  ValueError
Error:       Tweet 1234567890 deleted or inaccessible
Retry Count: 3
```

### Behaviour notes

- `quarantine_item` calls `mkdir(parents=True, exist_ok=True)` on the item dir — idempotent, overwrites existing files on re-quarantine after a failed retry
- `tweet.json` is not written when `tweet_data` is `None` (tweet was never successfully fetched)
- `remove_item` deletes the entire subdirectory; no error if the dir is already absent
- `list_quarantined_ids` reads the quarantine root and returns the names of entries that are directories — ignores root-level files (e.g. report files); does not touch the DB
- `generate_report` takes the retry session's results list, writes `quarantine_report_{timestamp}.txt` (timestamp format: `%Y%m%d_%H%M%S`) in the quarantine root, and returns the path

### `generate_report` results list entry shape

```python
{
    "tweet_id": str,
    "outcome": "success" | "failed",
    "error": Optional[str],           # present on failure
    "error_category": Optional[str],  # present on failure
    "retry_count": int,
}
```

### Report file format

```
Quarantine Retry Report — 2026-05-03T14:30:00
==============================================
Retried:   5
Succeeded: 3
Failed:    2

FAILURES
--------
Tweet ID:    1234567890
  Category:    permanent
  Error:       Tweet deleted or inaccessible
  Retry Count: 4

Tweet ID:    9876543210
  Category:    permanent
  Error:       Access denied
  Retry Count: 2
```

---

## `StateManager` additions

### `mark_quarantined`

```python
def mark_quarantined(
    self,
    tweet_id: str,
    error: str,
    retry_count: int = 0,
) -> None
```

Sets `status='quarantined'`, `last_error=error`, `retry_count=retry_count`. Mirrors the existing `mark_failed()` — no schema migration needed (`'quarantined'` is already a valid status value in the DB constraint).

### `get_quarantined_bookmarks`

```python
def get_quarantined_bookmarks(self, limit: int = 100) -> List[Dict]
```

Returns rows with `status='quarantined'` ordered by `updated_at DESC`, limited to `limit`. Mirrors the existing `get_failed_bookmarks()`.

---

## `retry_quarantine` flow

```
retry_quarantine(config, limit=None)
│
├── Initialise QuarantineManager(config), StateManager(config), TwitterClient
├── state_manager.get_quarantined_bookmarks(limit)
│
└── for each quarantined item:
    ├── 1. quarantine_manager.get_tweet_data(tweet_id)
    │       └── if found → _reprocess_tweet(tweet_data)  [Phase 8 stub]
    │
    ├── 2. If no stored data OR reprocess raised:
    │       └── twitter_client.get_tweet_details(tweet_id)
    │           └── _reprocess_tweet(fresh_data)
    │
    ├── 3a. SUCCESS:
    │       ├── quarantine_manager.remove_item(tweet_id)
    │       └── state_manager.mark_processed(tweet_id, 'success', ...)
    │
    └── 3b. FAILURE:
            ├── new_category = classify_error(exc)
            ├── quarantine_manager.quarantine_item(tweet_id, data, exc, new_category, retry_count+1)
            └── state_manager.mark_quarantined(tweet_id, str(exc), retry_count+1)

After loop:
├── print CLI summary to stdout
└── quarantine_manager.generate_report(results) → print report path
```

### `_reprocess_tweet` stub

```python
def _reprocess_tweet(tweet_data: Dict) -> None:
    raise NotImplementedError("_reprocess_tweet implemented in Phase 8")
```

This allows `retry_quarantine` to be fully wired end-to-end in Phase 7 without Phase 8 existing yet. Every retry attempt will hit the `NotImplementedError`, be caught as a failure, and re-quarantine the item. Phase 8 replaces the stub with real processing logic.

### CLI summary (stdout)

```
Quarantine retry: 5 items
  Succeeded: 3
  Failed:    2
  Report:    /path/to/logs/quarantine/quarantine_report_20260503_143000.txt
```

---

## Error Handling

| Operation | Error | Behaviour |
|-----------|-------|-----------|
| `quarantine_item` | `OSError` on write | Propagate — item not quarantined |
| `remove_item` | Item dir absent | Silently skip |
| `get_tweet_data` | Corrupt JSON | Return `None` (triggers API re-fetch in retry flow) |
| `generate_report` | `OSError` on write | Propagate |
| `get_quarantined_bookmarks` | DB error | Propagate |
| `mark_quarantined` | DB error | Propagate |

---

## Testing Strategy

All tests use `tmp_path`. No filesystem mocking.

### `tests/test_quarantine.py` — 14 tests

| Test | What it checks |
|------|----------------|
| `test_get_item_dir` | Returns `{quarantine_dir}/{tweet_id}` |
| `test_quarantine_item_creates_dir` | Subdirectory exists after call |
| `test_quarantine_item_writes_error_txt` | `error.txt` contains all expected fields |
| `test_quarantine_item_writes_tweet_json` | `tweet.json` written when `tweet_data` provided |
| `test_quarantine_item_no_tweet_json_when_none` | `tweet.json` absent when `tweet_data=None` |
| `test_quarantine_item_idempotent` | Second call overwrites cleanly, no error |
| `test_get_tweet_data_returns_dict` | Reads back the stored JSON correctly |
| `test_get_tweet_data_missing_returns_none` | Returns `None` when no `tweet.json` |
| `test_remove_item_deletes_dir` | Directory gone after call |
| `test_remove_item_missing_no_error` | No exception when item doesn't exist |
| `test_list_quarantined_ids` | Returns all subdirectory names, ignores root-level files |
| `test_list_quarantined_ids_empty` | Returns `[]` when quarantine dir is empty |
| `test_generate_report_writes_file` | Report file exists, contains correct counts and failure details |
| `test_classify_error_categories` | Each exception type maps to the correct `ErrorCategory` |

### `tests/test_state.py` — 4 new tests

| Test | What it checks |
|------|----------------|
| `test_mark_quarantined_sets_status` | DB row has `status='quarantined'` |
| `test_mark_quarantined_stores_error` | `last_error` and `retry_count` persisted correctly |
| `test_get_quarantined_bookmarks_returns_rows` | Returns quarantined rows only, not failed or success |
| `test_get_quarantined_bookmarks_limit` | Respects `limit` argument |

---

## Orchestrator Integration (Phase 8 contract)

Phase 7 ships before Phase 8 exists. The Phase 8 orchestrator must:

1. Construct `QuarantineManager(config)` once at startup alongside `StateManager`, `LocalStorage`, and `TwitterClient`
2. For each tweet that fails processing:
   - Call `classify_error(exc)` to determine the error category
   - If `RETRIABLE`: the API client has already exhausted its own retries; treat as `PERMANENT` at the orchestrator level unless a separate orchestrator-level retry budget is desired
   - If `PERMANENT`: call `quarantine_manager.quarantine_item(tweet_id, tweet_data, exc, category, retry_count)` then `state_manager.mark_quarantined(tweet_id, str(exc), retry_count)`
   - If `SKIP`: log and continue without quarantining
3. Replace `_reprocess_tweet` stub in `main.py` with the real processing pipeline
