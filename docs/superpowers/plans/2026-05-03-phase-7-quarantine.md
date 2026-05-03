# Phase 7: Error Handling & Quarantine System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement error classification, quarantine filesystem management, StateManager quarantine methods, and wire the existing `retry_quarantine` CLI stub.

**Architecture:** `QuarantineManager` (filesystem only, no StateManager coupling) lives in `storage/quarantine.py` alongside `ErrorCategory` and `classify_error`. `StateManager` in `storage/database.py` gets two new methods mirroring the existing `mark_failed`/`get_failed_bookmarks` pattern. `main.py`'s `retry_quarantine` stub is filled in, coordinating both managers plus a `_reprocess_tweet` placeholder that Phase 8 replaces.

**Tech Stack:** Python stdlib only — `json`, `shutil`, `enum`, `datetime`, `pathlib`. pytest with `tmp_path` (real filesystem, no mocking). `unittest.mock.MagicMock` for config stubs in tests.

---

## File Map

| File | Change |
|------|--------|
| `src/bookmark_downloader/storage/quarantine.py` | **Create** — `ErrorCategory`, `classify_error`, `QuarantineManager` |
| `src/bookmark_downloader/storage/database.py` | **Modify** — add `mark_quarantined`, `get_quarantined_bookmarks` to `StateManager` |
| `src/bookmark_downloader/main.py` | **Modify** — add `Dict` to typing imports, add `_reprocess_tweet` stub, fill in `retry_quarantine` |
| `tests/test_quarantine.py` | **Create** — 14 tests |
| `tests/test_state.py` | **Modify** — 4 new tests |

---

### Task 1: ErrorCategory enum + classify_error

**Files:**
- Create: `src/bookmark_downloader/storage/quarantine.py`
- Create: `tests/test_quarantine.py`

`classify_error` is a pure function that maps exceptions to `ErrorCategory`. `RateLimitError` is imported from `api.twitter_client` (safe — xdk is only loaded on `TwitterClient.__init__`, not at import time).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quarantine.py
from unittest.mock import MagicMock
from pathlib import Path

import pytest

from bookmark_downloader.api.twitter_client import RateLimitError
from bookmark_downloader.storage.quarantine import (
    ErrorCategory,
    QuarantineManager,
    classify_error,
)


def make_quarantine_manager(tmp_path: Path) -> QuarantineManager:
    config = MagicMock()
    config.get_quarantine_dir.return_value = tmp_path / "quarantine"
    return QuarantineManager(config)


def test_classify_error_categories():
    assert classify_error(RateLimitError("rate limit")) == ErrorCategory.RETRIABLE
    assert classify_error(TimeoutError()) == ErrorCategory.RETRIABLE
    assert classify_error(ConnectionError()) == ErrorCategory.RETRIABLE
    assert classify_error(ValueError("API error 500: server error")) == ErrorCategory.RETRIABLE
    assert classify_error(ValueError("API error 503: unavailable")) == ErrorCategory.RETRIABLE
    assert classify_error(ValueError("API error 404: not found")) == ErrorCategory.PERMANENT
    assert classify_error(ValueError("API error 403: forbidden")) == ErrorCategory.PERMANENT
    assert classify_error(ValueError("Missing required field: id")) == ErrorCategory.PERMANENT
    assert classify_error(PermissionError()) == ErrorCategory.PERMANENT
    assert classify_error(OSError()) == ErrorCategory.PERMANENT
    assert classify_error(RuntimeError("unexpected")) == ErrorCategory.PERMANENT
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_quarantine.py::test_classify_error_categories -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'bookmark_downloader.storage.quarantine'`

- [ ] **Step 3: Create quarantine.py with ErrorCategory + classify_error**

```python
# src/bookmark_downloader/storage/quarantine.py
"""Quarantine management for failed bookmark processing."""

import json
import shutil
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from bookmark_downloader.api.twitter_client import RateLimitError
from bookmark_downloader.config import Config
from bookmark_downloader.utils.logger import get_logger

logger = get_logger(__name__)


class ErrorCategory(Enum):
    RETRIABLE = "retriable"
    PERMANENT = "permanent"
    SKIP = "skip"


def classify_error(exc: Exception) -> ErrorCategory:
    """Classify an exception as RETRIABLE or PERMANENT. Never returns SKIP."""
    if isinstance(exc, RateLimitError):
        return ErrorCategory.RETRIABLE
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ErrorCategory.RETRIABLE
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "500" in msg or "503" in msg:
            return ErrorCategory.RETRIABLE
        return ErrorCategory.PERMANENT
    if isinstance(exc, (PermissionError, OSError)):
        return ErrorCategory.PERMANENT
    return ErrorCategory.PERMANENT
```

Do not add `QuarantineManager` yet — it comes in Task 2.

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_quarantine.py::test_classify_error_categories -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/test_quarantine.py src/bookmark_downloader/storage/quarantine.py
git commit -m "feat(quarantine): add ErrorCategory enum and classify_error"
```

---

### Task 2: QuarantineManager — get_item_dir + quarantine_item

**Files:**
- Modify: `src/bookmark_downloader/storage/quarantine.py`
- Modify: `tests/test_quarantine.py`

`quarantine_item` writes `error.txt` (always) and `tweet.json` (only when `tweet_data` is not `None`). It is idempotent — calling it twice on the same `tweet_id` overwrites files cleanly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quarantine.py`:

```python
def test_get_item_dir(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    assert qm.get_item_dir("tweet_123") == tmp_path / "quarantine" / "tweet_123"


def test_quarantine_item_creates_dir(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_123", None, ValueError("bad"), ErrorCategory.PERMANENT)
    assert (tmp_path / "quarantine" / "tweet_123").is_dir()


def test_quarantine_item_writes_error_txt(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item(
        "tweet_123", None, ValueError("bad tweet"), ErrorCategory.PERMANENT, retry_count=2
    )
    content = (tmp_path / "quarantine" / "tweet_123" / "error.txt").read_text()
    assert "Tweet ID:    tweet_123" in content
    assert "Category:    permanent" in content
    assert "Error Type:  ValueError" in content
    assert "Error:       bad tweet" in content
    assert "Retry Count: 2" in content
    assert "Quarantined:" in content


def test_quarantine_item_writes_tweet_json(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    data = {"id": "tweet_123", "text": "hello"}
    qm.quarantine_item("tweet_123", data, ValueError("bad"), ErrorCategory.PERMANENT)
    tweet_json = tmp_path / "quarantine" / "tweet_123" / "tweet.json"
    assert tweet_json.exists()
    import json
    assert json.loads(tweet_json.read_text()) == data


def test_quarantine_item_no_tweet_json_when_none(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_123", None, ValueError("bad"), ErrorCategory.PERMANENT)
    assert not (tmp_path / "quarantine" / "tweet_123" / "tweet.json").exists()


def test_quarantine_item_idempotent(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_123", None, ValueError("first"), ErrorCategory.PERMANENT)
    qm.quarantine_item("tweet_123", None, ValueError("second"), ErrorCategory.PERMANENT)
    content = (tmp_path / "quarantine" / "tweet_123" / "error.txt").read_text()
    assert "second" in content
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_quarantine.py -k "item_dir or quarantine_item" -v
```

Expected: all `FAILED` — `AttributeError: 'MagicMock' object ... QuarantineManager not defined`

- [ ] **Step 3: Add QuarantineManager with get_item_dir + quarantine_item**

Append to `src/bookmark_downloader/storage/quarantine.py` (after `classify_error`):

```python
class QuarantineManager:
    def __init__(self, config: Config) -> None:
        self._quarantine_dir = config.get_quarantine_dir()

    def get_item_dir(self, tweet_id: str) -> Path:
        return self._quarantine_dir / tweet_id

    def quarantine_item(
        self,
        tweet_id: str,
        tweet_data: Optional[Dict],
        error: Exception,
        error_category: ErrorCategory,
        retry_count: int = 0,
    ) -> Path:
        item_dir = self.get_item_dir(tweet_id)
        item_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        error_content = (
            f"Tweet ID:    {tweet_id}\n"
            f"Quarantined: {now}\n"
            f"Category:    {error_category.value}\n"
            f"Error Type:  {type(error).__name__}\n"
            f"Error:       {error}\n"
            f"Retry Count: {retry_count}\n"
        )
        (item_dir / "error.txt").write_text(error_content, encoding="utf-8")

        if tweet_data is not None:
            (item_dir / "tweet.json").write_text(
                json.dumps(tweet_data, indent=2), encoding="utf-8"
            )

        logger.debug("Quarantined tweet %s (category=%s)", tweet_id, error_category.value)
        return item_dir
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_quarantine.py -k "item_dir or quarantine_item" -v
```

Expected: 6 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/test_quarantine.py src/bookmark_downloader/storage/quarantine.py
git commit -m "feat(quarantine): add QuarantineManager with get_item_dir and quarantine_item"
```

---

### Task 3: QuarantineManager — get_tweet_data, remove_item, list_quarantined_ids

**Files:**
- Modify: `src/bookmark_downloader/storage/quarantine.py`
- Modify: `tests/test_quarantine.py`

`get_tweet_data` returns `None` on missing file OR corrupt JSON (both trigger API re-fetch in the retry flow). `remove_item` is silent when the dir is absent. `list_quarantined_ids` returns directory names only — root-level files (e.g. report files) are excluded.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quarantine.py`:

```python
def test_get_tweet_data_returns_dict(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    data = {"id": "tweet_123", "text": "hello world"}
    qm.quarantine_item("tweet_123", data, ValueError("bad"), ErrorCategory.PERMANENT)
    assert qm.get_tweet_data("tweet_123") == data


def test_get_tweet_data_missing_returns_none(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    # Missing item dir → None
    assert qm.get_tweet_data("nonexistent") is None
    # Corrupt JSON → None (triggers API re-fetch in retry flow)
    item_dir = tmp_path / "quarantine" / "tweet_corrupt"
    item_dir.mkdir(parents=True)
    (item_dir / "tweet.json").write_text("{ not valid json !!!", encoding="utf-8")
    assert qm.get_tweet_data("tweet_corrupt") is None


def test_remove_item_deletes_dir(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_123", None, ValueError("bad"), ErrorCategory.PERMANENT)
    qm.remove_item("tweet_123")
    assert not (tmp_path / "quarantine" / "tweet_123").exists()


def test_remove_item_missing_no_error(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.remove_item("nonexistent")  # must not raise


def test_list_quarantined_ids(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    qm.quarantine_item("tweet_aaa", None, ValueError("bad"), ErrorCategory.PERMANENT)
    qm.quarantine_item("tweet_bbb", None, ValueError("bad"), ErrorCategory.PERMANENT)
    # root-level file should be ignored
    (tmp_path / "quarantine" / "quarantine_report_20260503.txt").write_text("report")
    ids = qm.list_quarantined_ids()
    assert set(ids) == {"tweet_aaa", "tweet_bbb"}


def test_list_quarantined_ids_empty(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    assert qm.list_quarantined_ids() == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_quarantine.py -k "tweet_data or remove_item or list_quarantined" -v
```

Expected: all `FAILED` — `AttributeError: 'QuarantineManager' object has no attribute 'get_tweet_data'`

- [ ] **Step 3: Add the three methods to QuarantineManager**

Append inside the `QuarantineManager` class in `src/bookmark_downloader/storage/quarantine.py`:

```python
    def get_tweet_data(self, tweet_id: str) -> Optional[Dict]:
        tweet_json = self.get_item_dir(tweet_id) / "tweet.json"
        if not tweet_json.exists():
            return None
        try:
            return json.loads(tweet_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def remove_item(self, tweet_id: str) -> None:
        item_dir = self.get_item_dir(tweet_id)
        if item_dir.exists():
            shutil.rmtree(item_dir)
            logger.debug("Removed quarantine item %s", tweet_id)

    def list_quarantined_ids(self) -> List[str]:
        if not self._quarantine_dir.exists():
            return []
        return [
            entry.name
            for entry in self._quarantine_dir.iterdir()
            if entry.is_dir()
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_quarantine.py -k "tweet_data or remove_item or list_quarantined" -v
```

Expected: 6 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/test_quarantine.py src/bookmark_downloader/storage/quarantine.py
git commit -m "feat(quarantine): add get_tweet_data, remove_item, list_quarantined_ids"
```

---

### Task 4: QuarantineManager — generate_report

**Files:**
- Modify: `src/bookmark_downloader/storage/quarantine.py`
- Modify: `tests/test_quarantine.py`

`generate_report` takes a list of result dicts from the retry session and writes a timestamped report file to the quarantine root. Returns the report path.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_quarantine.py`:

```python
def test_generate_report_writes_file(tmp_path):
    qm = make_quarantine_manager(tmp_path)
    results = [
        {"tweet_id": "tweet_111", "outcome": "success", "retry_count": 1},
        {
            "tweet_id": "tweet_456",
            "outcome": "failed",
            "error": "something went wrong",
            "error_category": "permanent",
            "retry_count": 3,
        },
    ]
    report_path = qm.generate_report(results)
    assert report_path.exists()
    content = report_path.read_text()
    assert "Retried:   2" in content
    assert "Succeeded: 1" in content
    assert "Failed:    1" in content
    assert "tweet_456" in content
    assert "something went wrong" in content
    assert "permanent" in content
    assert "Retry Count: 3" in content
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_quarantine.py::test_generate_report_writes_file -v
```

Expected: `FAILED` — `AttributeError: 'QuarantineManager' object has no attribute 'generate_report'`

- [ ] **Step 3: Add generate_report to QuarantineManager**

Append inside the `QuarantineManager` class in `src/bookmark_downloader/storage/quarantine.py`:

```python
    def generate_report(self, results: List[Dict]) -> Path:
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        report_path = self._quarantine_dir / f"quarantine_report_{timestamp}.txt"

        succeeded = [r for r in results if r["outcome"] == "success"]
        failed = [r for r in results if r["outcome"] == "failed"]

        header_date = now.strftime("%Y-%m-%dT%H:%M:%S")
        title = f"Quarantine Retry Report — {header_date}"
        lines = [
            title,
            "=" * len(title),
            f"Retried:   {len(results)}",
            f"Succeeded: {len(succeeded)}",
            f"Failed:    {len(failed)}",
        ]

        if failed:
            lines += ["", "FAILURES", "--------"]
            for r in failed:
                lines += [
                    f"Tweet ID:    {r['tweet_id']}",
                    f"  Category:    {r.get('error_category', 'unknown')}",
                    f"  Error:       {r.get('error', 'unknown')}",
                    f"  Retry Count: {r['retry_count']}",
                    "",
                ]

        self._quarantine_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("Generated quarantine report at %s", report_path)
        return report_path
```

- [ ] **Step 4: Run all quarantine tests to verify 14 pass**

```bash
.venv/bin/pytest tests/test_quarantine.py -v
```

Expected: 14 `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/test_quarantine.py src/bookmark_downloader/storage/quarantine.py
git commit -m "feat(quarantine): add generate_report"
```

---

### Task 5: StateManager additions — mark_quarantined + get_quarantined_bookmarks

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

Both methods mirror the existing `mark_failed` / `get_failed_bookmarks` pattern exactly. The DB schema already supports `status='quarantined'` — no migration needed.

The existing `state_manager` fixture in `tests/conftest.py` provides a real SQLite DB via `tmp_path`. Use it directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_state.py`:

```python
def test_mark_quarantined_sets_status(state_manager):
    state_manager.mark_quarantined("tweet_q1", "tweet deleted", retry_count=0)
    from bookmark_downloader.storage.database import Database
    # Use internal DB access to verify — same pattern as existing tests
    bookmark = state_manager._db._get_bookmark("tweet_q1")
    assert bookmark["status"] == "quarantined"


def test_mark_quarantined_stores_error(state_manager):
    state_manager.mark_quarantined("tweet_q2", "access denied", retry_count=3)
    bookmark = state_manager._db._get_bookmark("tweet_q2")
    assert bookmark["last_error"] == "access denied"
    assert bookmark["retry_count"] == 3


def test_get_quarantined_bookmarks_returns_rows(state_manager):
    state_manager.mark_quarantined("tweet_q3", "error a")
    state_manager.mark_failed("tweet_f1", "error b")
    state_manager.mark_processed("tweet_s1", "success", [], 0)
    rows = state_manager.get_quarantined_bookmarks()
    ids = [r["tweet_id"] for r in rows]
    assert "tweet_q3" in ids
    assert "tweet_f1" not in ids
    assert "tweet_s1" not in ids


def test_get_quarantined_bookmarks_limit(state_manager):
    for i in range(5):
        state_manager.mark_quarantined(f"tweet_lim_{i}", "error")
    rows = state_manager.get_quarantined_bookmarks(limit=3)
    assert len(rows) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_state.py -k "quarantined" -v
```

Expected: all `FAILED` — `AttributeError: 'StateManager' object has no attribute 'mark_quarantined'`

- [ ] **Step 3: Add the two methods to StateManager in database.py**

In `src/bookmark_downloader/storage/database.py`, add after the `mark_failed` method (around line 194):

```python
    def mark_quarantined(
        self,
        tweet_id: str,
        error: str,
        retry_count: int = 0,
    ) -> None:
        self._db._upsert_bookmark(
            tweet_id,
            status="quarantined",
            last_error=error,
            retry_count=retry_count,
        )
        self._db._log_history(tweet_id, "quarantined", error)

    def get_quarantined_bookmarks(self, limit: int = 100) -> List[Dict]:
        cursor = self._db._conn.execute(
            """SELECT * FROM bookmarks
               WHERE status = 'quarantined'
               ORDER BY updated_at DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
```

- [ ] **Step 4: Run all state tests to verify no regressions**

```bash
.venv/bin/pytest tests/test_state.py -v
```

Expected: all pre-existing tests `PASSED` plus 4 new `PASSED`

- [ ] **Step 5: Commit**

```bash
git add tests/test_state.py src/bookmark_downloader/storage/database.py
git commit -m "feat(state): add mark_quarantined and get_quarantined_bookmarks to StateManager"
```

---

### Task 6: _reprocess_tweet stub + retry_quarantine

**Files:**
- Modify: `src/bookmark_downloader/main.py`

No new tests in this task — the spec has none for `retry_quarantine` in Phase 7. The implementation is wired end-to-end; every retry attempt will re-quarantine because `_reprocess_tweet` always raises `NotImplementedError`. Phase 8 replaces the stub.

- [ ] **Step 1: Add Dict to typing imports in main.py**

Current line (around line 9):
```python
from typing import Optional
```

Replace with:
```python
from typing import Dict, Optional
```

- [ ] **Step 2: Add new top-level imports to main.py**

After the existing imports block (after `from bookmark_downloader.utils.logger import Logger, get_logger`), add:

```python
from bookmark_downloader.api.twitter_client import BookmarkClient
from bookmark_downloader.storage.database import StateManager
from bookmark_downloader.storage.quarantine import ErrorCategory, QuarantineManager, classify_error
```

- [ ] **Step 3: Add _reprocess_tweet stub before retry_quarantine**

In `main.py`, add this function immediately before `retry_quarantine` (around line 123):

```python
def _reprocess_tweet(tweet_data: Dict) -> None:
    raise NotImplementedError("_reprocess_tweet implemented in Phase 8")
```

- [ ] **Step 4: Replace retry_quarantine body**

Replace the current `retry_quarantine` function body (keep the signature and outer try/except):

```python
def retry_quarantine(config, limit: Optional[int] = None) -> bool:
    """Retry failed downloads from quarantine."""
    logger = get_logger(__name__)

    try:
        quarantine_manager = QuarantineManager(config)
        state_manager = StateManager(config)
        bookmark_client = BookmarkClient(config)

        quarantined = state_manager.get_quarantined_bookmarks(limit or 100)
        logger.info("Found %d quarantined items to retry", len(quarantined))

        results = []
        for item in quarantined:
            tweet_id = item["tweet_id"]
            retry_count = item.get("retry_count", 0)
            tweet_data = None
            exc = None

            # Try stored JSON first
            stored_data = quarantine_manager.get_tweet_data(tweet_id)
            if stored_data is not None:
                try:
                    _reprocess_tweet(stored_data)
                    tweet_data = stored_data
                except Exception as e:
                    exc = e
                    tweet_data = stored_data

            # Fall back to API if no stored data or reprocess failed
            if stored_data is None or exc is not None:
                try:
                    fresh_data = bookmark_client.get_tweet_details(tweet_id)
                    tweet_data = fresh_data
                    exc = None
                    _reprocess_tweet(fresh_data)
                except Exception as e:
                    exc = e

            if exc is None:
                quarantine_manager.remove_item(tweet_id)
                state_manager.mark_processed(tweet_id, "success", [], 0)
                results.append({
                    "tweet_id": tweet_id,
                    "outcome": "success",
                    "retry_count": retry_count,
                })
                logger.info("Successfully reprocessed %s", tweet_id)
            else:
                category = classify_error(exc)
                quarantine_manager.quarantine_item(tweet_id, tweet_data, exc, category, retry_count + 1)
                state_manager.mark_quarantined(tweet_id, str(exc), retry_count + 1)
                results.append({
                    "tweet_id": tweet_id,
                    "outcome": "failed",
                    "error": str(exc),
                    "error_category": category.value,
                    "retry_count": retry_count + 1,
                })
                logger.warning("Failed to reprocess %s: %s", tweet_id, exc)

        succeeded = sum(1 for r in results if r["outcome"] == "success")
        failed = sum(1 for r in results if r["outcome"] == "failed")
        report_path = quarantine_manager.generate_report(results)

        print(f"Quarantine retry: {len(results)} items")
        print(f"  Succeeded: {succeeded}")
        print(f"  Failed:    {failed}")
        print(f"  Report:    {report_path}")

        state_manager.close()
        return True

    except Exception as e:
        logger.error(f"Quarantine retry failed: {e}", exc_info=True)
        return False
```

- [ ] **Step 5: Run the full test suite to verify no regressions**

```bash
.venv/bin/pytest tests/test_quarantine.py tests/test_state.py tests/test_config.py tests/test_main.py -v
```

Expected: all pass. If `test_main.py` has any test that patches `retry_quarantine` internals, update those patches to reflect the new imports.

- [ ] **Step 6: Commit**

```bash
git add src/bookmark_downloader/main.py
git commit -m "feat(main): wire retry_quarantine with QuarantineManager and _reprocess_tweet stub"
```

---

## Final check

```bash
.venv/bin/pytest tests/test_quarantine.py tests/test_state.py -v
```

Expected: **18 passed** (14 quarantine + 4 state).
