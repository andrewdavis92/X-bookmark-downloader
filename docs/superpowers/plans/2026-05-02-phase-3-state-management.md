# Phase 3: State Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement SQLite-backed state tracking so the downloader can detect already-processed bookmarks and collect processing statistics.

**Architecture:** A single `storage/database.py` module exposes two classes — a low-level `Database` that owns the SQLite connection and schema, and a higher-level `StateManager` that the orchestrator (Phase 8) calls directly. Schema versioning uses a `schema_version` table so future migrations can run safely on startup.

**Tech Stack:** Python 3.9+ stdlib `sqlite3`, `dataclasses`, `datetime` — no new dependencies.

---

## Decisions Made (pre-plan clarification)

| # | Decision |
|---|----------|
| File layout | `StateManager` + `Database` both live in `src/bookmark_downloader/storage/database.py` |
| `quoted_posts` FK | FK on `quoted_tweet_id` dropped — quoted tweets are usually not bookmarked |
| Method name | `get_failed_bookmarks()` (matches class spec) |
| `update_status` | General setter: `update_status(tweet_id, status, error=None)` |
| Migrations | Simple `schema_version` table, integer version, checked on startup |
| `ProcessingStats` | `@dataclass` with 5 fields |
| `author_username`/`author_id` | Nullable (plan said NOT NULL but `StateManager` API doesn't supply them) |

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `src/bookmark_downloader/storage/database.py` | `ProcessingStats` dataclass, `Database` class, `StateManager` class |
| Modify | `tests/conftest.py` | Add `db_path`, `db`, `state_manager` fixtures |
| Create | `tests/test_state.py` | All Phase 3 tests (~35) |

---

## Task 1: Scaffold + `ProcessingStats` dataclass ✅

**Files:**
- Create: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_state.py`

- [x] **Step 1: Write the failing test**
- [x] **Step 2: Run test to verify it fails**
- [x] **Step 3: Create the scaffold**
- [x] **Step 4: Run test to verify it passes**
- [x] **Step 5: Add test fixtures to conftest.py**
- [x] **Step 6: Commit**

### ✅ Task 1 Review Notes
- **Spec:** Compliant — `ProcessingStats` dataclass, `SCHEMA_VERSION`, 3 tests, 4 fixtures all present
- **Quality:** Approved — clean imports, correct use of `yield` in fixtures

---

## Task 2: Database initialization + schema versioning ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement `Database` class**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

### ✅ Task 2 Review Notes
- **Spec:** Compliant — `Database` class with all 5 tables, schema versioning, 4 tests passing; `quoted_posts.quoted_tweet_id` correctly has no FK constraint
- **Quality:** Fixed double-close in `test_database_reopen_is_idempotent` — removed manual `db.close()` from test body (fixture handles teardown)
- **Note:** `processing_history.tweet_id` intentionally has no FK to `bookmarks` — history entries survive bookmark deletion

---

## Task 3: Bookmarks table CRUD ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement bookmark CRUD methods in `Database`**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

### ✅ Task 3 Review Notes
- **Spec:** Compliant — 6 tests pass, all 3 methods present with correct signatures
- **Quality:** Approved — f-string column interpolation in `_upsert_bookmark` is acceptable for internal methods (no external input reaches call sites); identity fields correctly protected on update

---

## Task 4: Processing history logging (`_log_history`) ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement `_log_history` in `Database`**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

---

## Task 5: `StateManager` construction + `close()` ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement `StateManager.__init__` and `close()`**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

---

## Task 6: `is_already_processed()` + `mark_processed()` ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement methods in `StateManager`**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

---

## Task 7: `mark_failed()` ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement `mark_failed` in `StateManager`**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

---

## Task 8: `update_status()` ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement `update_status` in `StateManager`**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

---

## Task 9: `get_failed_bookmarks()` ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement `get_failed_bookmarks` in `StateManager`**
- [x] **Step 4: Run to verify pass**
- [x] **Step 5: Commit**

---

## Task 10: `get_processing_stats()` + `clear_old_entries()` ✅

**Files:**
- Modify: `src/bookmark_downloader/storage/database.py`
- Modify: `tests/test_state.py`

- [x] **Step 1: Write the failing tests**
- [x] **Step 2: Run to verify failure**
- [x] **Step 3: Implement both methods in `StateManager`**
- [x] **Step 4: Run the full test suite**
- [x] **Step 5: Run all tests to check for regressions**
- [x] **Step 6: Commit**

### ✅ Tasks 4–10 Review Notes
- **Spec:** All 9 StateManager methods present with correct signatures; 45/45 tests pass; `ProcessingStats` dataclass returned (not dict); `clear_old_entries` correctly only deletes `status = 'success'` rows
- **Quality:** Approved — no dead imports, all previously-scaffolded imports (`Dict`, `List`, `timedelta`) actively used; `datetime.utcnow()` deprecated in Python 3.12+ but functional and consistent throughout
- **No regressions** in `test_config.py`, `test_main.py`, `test_logger.py`

---

## Self-Review Checklist ✅ COMPLETE

**Spec coverage:**
- [x] Database initialization — Task 2
- [x] CRUD operations — Tasks 3, 4
- [x] Transaction handling — `_conn.commit()` called after every write
- [x] "Connection pooling" (simplified to single shared connection) — Task 2
- [x] `mark_processed()` — Task 6
- [x] `is_already_processed()` — Task 6
- [x] `get_failed_bookmarks()` (was `get_failed_items` in task list) — Task 9
- [x] `update_status()` — Task 8
- [x] `mark_failed()` — Task 7
- [x] `get_processing_stats()` — Task 10
- [x] `clear_old_entries()` — Task 10
- [x] Schema versioning — Task 2
- [x] `ProcessingStats` dataclass — Task 1
- [x] `quoted_posts` FK fix (dropped FK on `quoted_tweet_id`) — Task 2 schema
- [x] `test_state.py` — created across all tasks
