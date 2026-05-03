# Phase 5: Quote Post Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement quote tweet detection so the Phase 8 orchestrator can identify when a bookmarked tweet quotes another tweet and route it through the normal processing pipeline.

**Architecture:** A single pure function `extract_quoted_tweet_id(tweet_data) -> Optional[str]` in `processing/quote_resolver.py` reads the already-mapped `quoted_tweet_id` field from a `TweetData` dict. The mapping from raw X API `referenced_tweets` to that field is performed by the API client (`twitter_client.py`), which is also fixed in this phase to use the correct expansion key (`referenced_tweets.id` instead of the currently broken `quote.id`).

**Tech Stack:** Python 3.9+, pytest, existing `bookmark_downloader` package structure. No new dependencies.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/bookmark_downloader/api/types.py` | Modify | Add `referenced_tweets` field to `TweetData` TypedDict |
| `src/bookmark_downloader/api/twitter_client.py` | Modify | Fix expansion keys; add `_map_quoted_tweet_id`; call it in both response-parsing paths |
| `src/bookmark_downloader/processing/quote_resolver.py` | Create | Single public function: `extract_quoted_tweet_id` |
| `tests/test_api.py` | Modify | Add 3 tests for `_map_quoted_tweet_id` |
| `tests/test_processing.py` | Create | 4 tests for `extract_quoted_tweet_id` |

---

## Task 1: Add `referenced_tweets` to `TweetData`

**Files:**
- Modify: `src/bookmark_downloader/api/types.py`

This is a type-only change — no runtime behaviour, no tests needed. It unblocks Task 2.

- [ ] **Step 1: Update `TweetData` in `api/types.py`**

Open `src/bookmark_downloader/api/types.py`. The current `TweetData` class ends at line 38. Replace it with:

```python
class TweetData(TypedDict):
    """Tweet object from X API."""

    id: str
    text: str
    author_id: NotRequired[str]
    created_at: NotRequired[str]
    attachments: NotRequired[Dict[str, List[str]]]  # e.g. {"media_keys": ["7_1234"]}
    referenced_tweets: NotRequired[List[Dict[str, str]]]  # raw from API; e.g. [{"type": "quoted", "id": "9876"}]
    quoted_tweet_id: NotRequired[str]  # mapped by client from referenced_tweets
```

No import changes needed — `List` and `Dict` are already imported at the top of the file.

- [ ] **Step 2: Commit**

```bash
git add src/bookmark_downloader/api/types.py
git commit -m "feat(api): add referenced_tweets and quoted_tweet_id fields to TweetData"
```

---

## Task 2: Fix `twitter_client.py` — expansion keys + `_map_quoted_tweet_id`

**Files:**
- Modify: `src/bookmark_downloader/api/twitter_client.py:14-19` (DEFAULT_EXPANSIONS)
- Modify: `src/bookmark_downloader/api/twitter_client.py` (new method + two call sites)
- Test: `tests/test_api.py`

- [ ] **Step 1: Write 3 failing tests in `test_api.py`**

Add the following class at the end of `tests/test_api.py`, before any existing test classes or after the last one:

```python
class TestMapQuotedTweetId:
    """Test _map_quoted_tweet_id helper method."""

    @patch("xdk.client.Client")
    def test_returns_quoted_id_when_type_is_quoted(self, mock_xdk_client: Mock):
        client = TwitterClient(access_token="test_token")
        result = client._map_quoted_tweet_id({
            "referenced_tweets": [{"type": "quoted", "id": "9876543210"}]
        })
        assert result == "9876543210"

    @patch("xdk.client.Client")
    def test_returns_none_when_type_is_replied_to(self, mock_xdk_client: Mock):
        client = TwitterClient(access_token="test_token")
        result = client._map_quoted_tweet_id({
            "referenced_tweets": [{"type": "replied_to", "id": "9876543210"}]
        })
        assert result is None

    @patch("xdk.client.Client")
    def test_returns_none_when_no_referenced_tweets(self, mock_xdk_client: Mock):
        client = TwitterClient(access_token="test_token")
        result = client._map_quoted_tweet_id({})
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py::TestMapQuotedTweetId -v
```

Expected: 3 failures with `AttributeError: 'TwitterClient' object has no attribute '_map_quoted_tweet_id'`

- [ ] **Step 3: Fix `DEFAULT_EXPANSIONS` in `twitter_client.py`**

`DEFAULT_EXPANSIONS` is at lines 14–19. Replace it:

```python
DEFAULT_EXPANSIONS = {
    "expansions": ["author_id", "created_at", "attachments.media_keys", "referenced_tweets.id"],
    "media_fields": ["type", "url", "alt_text"],
    "user_fields": ["username", "created_at"],
    "tweet_fields": ["text", "author_id", "created_at", "attachments", "referenced_tweets"],
}
```

- [ ] **Step 4: Add `_map_quoted_tweet_id` method to `TwitterClient`**

Add this method to `TwitterClient` after `_build_expansions_params` (around line 116) and before `get_bookmarks_iter`:

```python
def _map_quoted_tweet_id(self, tweet: Dict) -> Optional[str]:
    for ref in tweet.get("referenced_tweets", []):
        if ref.get("type") == "quoted":
            return ref["id"]
    return None
```

`Optional` is already imported at the top of the file via `from typing import Any, Dict, Generator, List, Optional`.

- [ ] **Step 5: Call `_map_quoted_tweet_id` in `get_bookmarks_iter`**

In `get_bookmarks_iter`, find the tweet yield loop (around line 180). It currently reads:

```python
for tweet in tweets:
    try:
        self._validate_tweet(tweet)
        yield tweet
    except ValueError as e:
        logger.error(f"Invalid tweet data for ID {tweet.get('id')}: {e}")
        raise
```

Replace with:

```python
for tweet in tweets:
    try:
        self._validate_tweet(tweet)
        quoted_id = self._map_quoted_tweet_id(tweet)
        if quoted_id:
            tweet["quoted_tweet_id"] = quoted_id
        yield tweet
    except ValueError as e:
        logger.error(f"Invalid tweet data for ID {tweet.get('id')}: {e}")
        raise
```

- [ ] **Step 6: Call `_map_quoted_tweet_id` in `get_tweet_details`**

In `get_tweet_details`, find where `_validate_tweet` is called and the tweet is returned (around line 253). It currently reads:

```python
self._validate_tweet(tweet)
return tweet
```

Replace with:

```python
self._validate_tweet(tweet)
quoted_id = self._map_quoted_tweet_id(tweet)
if quoted_id:
    tweet["quoted_tweet_id"] = quoted_id
return tweet
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/test_api.py::TestMapQuotedTweetId -v
```

Expected output:
```
tests/test_api.py::TestMapQuotedTweetId::test_returns_quoted_id_when_type_is_quoted PASSED
tests/test_api.py::TestMapQuotedTweetId::test_returns_none_when_type_is_replied_to PASSED
tests/test_api.py::TestMapQuotedTweetId::test_returns_none_when_no_referenced_tweets PASSED
3 passed
```

- [ ] **Step 8: Run the full test suite to check for regressions**

```bash
pytest tests/test_api.py -v
```

Expected: all previously passing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add src/bookmark_downloader/api/twitter_client.py tests/test_api.py
git commit -m "feat(api): fix referenced_tweets expansion and map quoted_tweet_id in TweetData"
```

---

## Task 3: Implement `processing/quote_resolver.py`

**Files:**
- Create: `src/bookmark_downloader/processing/quote_resolver.py`
- Create: `tests/test_processing.py`

- [ ] **Step 1: Write 4 failing tests in a new `tests/test_processing.py`**

Create the file `tests/test_processing.py` with this content:

```python
"""Tests for processing module."""

import pytest

from bookmark_downloader.processing.quote_resolver import extract_quoted_tweet_id


def test_returns_quoted_id_when_present():
    tweet = {"id": "111", "text": "hello", "author_id": "222", "quoted_tweet_id": "9876543210"}
    assert extract_quoted_tweet_id(tweet) == "9876543210"


def test_returns_none_when_quoted_tweet_id_absent():
    tweet = {"id": "111", "text": "hello", "author_id": "222"}
    assert extract_quoted_tweet_id(tweet) is None


def test_returns_none_for_empty_string():
    tweet = {"id": "111", "text": "hello", "author_id": "222", "quoted_tweet_id": ""}
    assert extract_quoted_tweet_id(tweet) is None


def test_ignores_raw_referenced_tweets():
    # quote_resolver reads quoted_tweet_id only (already mapped by client);
    # it does NOT re-parse referenced_tweets itself
    tweet = {
        "id": "111",
        "text": "hello",
        "author_id": "222",
        "referenced_tweets": [{"type": "replied_to", "id": "9876543210"}],
    }
    assert extract_quoted_tweet_id(tweet) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_processing.py -v
```

Expected: 4 failures with `ModuleNotFoundError: No module named 'bookmark_downloader.processing.quote_resolver'`

- [ ] **Step 3: Create `processing/quote_resolver.py`**

Create `src/bookmark_downloader/processing/quote_resolver.py` with this content:

```python
"""Quote post detection for X bookmark downloader."""

from typing import Optional

from bookmark_downloader.api.types import TweetData
from bookmark_downloader.utils.logger import get_logger

logger = get_logger(__name__)


def extract_quoted_tweet_id(tweet_data: TweetData) -> Optional[str]:
    quoted_id = tweet_data.get("quoted_tweet_id")
    if quoted_id:
        logger.debug("Tweet %s quotes tweet %s", tweet_data.get("id"), quoted_id)
        return quoted_id
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_processing.py -v
```

Expected output:
```
tests/test_processing.py::test_returns_quoted_id_when_present PASSED
tests/test_processing.py::test_returns_none_when_quoted_tweet_id_absent PASSED
tests/test_processing.py::test_returns_none_for_empty_string PASSED
tests/test_processing.py::test_ignores_raw_referenced_tweets PASSED
4 passed
```

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass with no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/bookmark_downloader/processing/quote_resolver.py tests/test_processing.py
git commit -m "feat(processing): add quote_resolver with extract_quoted_tweet_id"
```
