# Phase 5: Quote Post Handling — Design Spec

**Date:** 2026-05-03  
**Status:** Approved  
**Depends on:** Phase 2 (API client & types), Phase 3 (state management), Phase 4 (media download engine)

---

## Goal

Implement quote post detection so the Phase 8 orchestrator can identify when a bookmarked tweet quotes another tweet and route it through the same processing pipeline. Phase 5 itself is a single pure-data function — no API calls, no I/O, no side effects.

---

## Scope

**In scope:**
- `processing/quote_resolver.py` with one public function: `extract_quoted_tweet_id`
- Fix `twitter_client.py` to map `referenced_tweets[type=quoted].id → TweetData.quoted_tweet_id`
- Fix the invalid `"quote.id"` expansion to `"referenced_tweets.id"` in `DEFAULT_EXPANSIONS`
- Add `"referenced_tweets"` to `tweet_fields` in `DEFAULT_EXPANSIONS`
- Update `TweetData` TypedDict with a `referenced_tweets` field

**Out of scope:**
- Fetching the quoted tweet from the API (orchestrator's job)
- Downloading quoted tweet media (Phase 4 + orchestrator)
- Saving quoted tweet text (Phase 6 + orchestrator)
- Creating symlinks (Phase 6)
- Recording `quoted_posts` DB relationships (Phase 8 orchestrator)
- Enforcing the one-level depth limit (Phase 8 orchestrator)
- Deduplication of quoted tweets across bookmarks (handled by existing `StateManager.is_already_processed`)

---

## Architecture

### Design decision: Option A — minimal gate, orchestrator drives behaviour

Quoted tweets are just tweets. Phase 5's only job is to detect whether a tweet references a quote and return the ID. All downstream behaviour — fetching, processing, downloading, symlinking, state recording — is the orchestrator's responsibility, exactly as it is for top-level bookmarks.

The one-level depth limit is enforced in the orchestrator via a `depth` integer passed through its internal tweet-processing function: `0` for top-level bookmarks, `1` when already processing a quoted tweet. Phase 5 never sees or enforces this.

### Files

| File | Change |
|------|--------|
| `src/bookmark_downloader/processing/quote_resolver.py` | **New** — single public function |
| `src/bookmark_downloader/api/types.py` | **Modified** — add `referenced_tweets` field to `TweetData`; add `"referenced_tweets"` to `tweet_fields` expansion |
| `src/bookmark_downloader/api/twitter_client.py` | **Modified** — fix expansion key; add `_map_quoted_tweet_id` mapping |
| `tests/test_processing.py` | **New** — quote resolver tests |
| `tests/test_api.py` | **Modified** — 3 new tests for `_map_quoted_tweet_id` |

---

## `processing/quote_resolver.py`

### Public interface

```python
def extract_quoted_tweet_id(tweet_data: TweetData) -> Optional[str]
```

### Behaviour

1. Read `tweet_data.get("quoted_tweet_id")`
2. If the value is a non-empty string, return it
3. Otherwise return `None`
4. Log at DEBUG level when a quoted tweet ID is found

The function has no API calls, no I/O, no side effects. It is a pure data accessor over an already-populated `TweetData` dict.

---

## `api/types.py` changes

Add `referenced_tweets` as a `NotRequired` field to `TweetData` to represent the raw API shape, alongside the existing mapped `quoted_tweet_id` field:

```python
class TweetData(TypedDict):
    id: str
    text: str
    author_id: NotRequired[str]
    created_at: NotRequired[str]
    attachments: NotRequired[Dict[str, List[str]]]
    referenced_tweets: NotRequired[List[Dict[str, str]]]  # raw from API
    quoted_tweet_id: NotRequired[str]                     # mapped by client
```

---

## `twitter_client.py` changes

### Fix expansion key and tweet_fields

`DEFAULT_EXPANSIONS` currently uses `"quote.id"` which is not a valid X API v2 expansion. Replace with `"referenced_tweets.id"` and add `"referenced_tweets"` to `tweet_fields` so the API returns the raw data:

```python
DEFAULT_EXPANSIONS = {
    "expansions": ["author_id", "attachments.media_keys", "referenced_tweets.id"],
    "tweet_fields": ["text", "author_id", "created_at", "attachments", "referenced_tweets"],
    ...
}
```

### Add `_map_quoted_tweet_id`

Add a private helper that extracts the quoted tweet ID from the raw `referenced_tweets` array and writes it into the `TweetData` dict. Call it in both `get_bookmarks_iter` and `get_tweet_details` when building a `TweetData` dict from the raw API response:

```python
def _map_quoted_tweet_id(self, tweet: Dict) -> Optional[str]:
    for ref in tweet.get("referenced_tweets", []):
        if ref.get("type") == "quoted":
            return ref["id"]
    return None
```

After this mapping, all downstream consumers (including `extract_quoted_tweet_id`) read a clean `quoted_tweet_id` field and never need to know about the raw `referenced_tweets` shape.

---

## Orchestrator integration (Phase 8 contract)

Phase 5 ships before Phase 8 exists. This section documents the contract Phase 8 must honour.

```
For each bookmark tweet (depth=0):
  1. quoted_id = extract_quoted_tweet_id(tweet_data)
  2. If None: no quote, continue normal processing
  3. If quoted_id is not None AND depth == 0:
       a. Check StateManager.is_already_processed(quoted_id)
          - If True: skip download, but still record the quoted_posts relationship
            and create symlinks pointing to the already-downloaded media
          - If False: fetch via twitter_client.get_tweet_details(quoted_id),
            then run normal tweet processing pipeline with depth=1
  4. If quoted_id is not None AND depth == 1:
       - Log DEBUG "quoted tweet has its own quote, skipping (max depth reached)"
       - Ignore the nested quote
```

**Deduplication:** `StateManager.is_already_processed(quoted_id)` returns `True` if the quoted tweet was previously downloaded — whether as a direct bookmark or as the quoted tweet of an earlier bookmark. No special handling is needed; the existing state DB schema covers this.

**DB relationship:** The orchestrator records the parent↔quote link in the `quoted_posts` table (already created in Phase 3) after the quoted tweet is processed.

---

## Error handling

Phase 5 itself has no error paths — it is a pure dict read with no I/O.

Errors that arise downstream of `extract_quoted_tweet_id` (e.g. the quoted tweet is deleted, access is denied) are handled by the existing error classification in `twitter_client.py` and the orchestrator's quarantine logic (Phase 7), using the same rules as any other tweet:

| Error | Behaviour |
|---|---|
| Quoted tweet deleted (404) | Log warning, skip quote, continue processing parent |
| Access denied (403) | Quarantine parent tweet for review |
| API error on fetch | Retry with backoff; quarantine if all attempts fail |

---

## Testing strategy

### `tests/test_processing.py` (new, 4 tests)

| Test | Input | Expected |
|---|---|---|
| Tweet with `quoted_tweet_id` | `TweetData` with `quoted_tweet_id="9876"` | returns `"9876"` |
| Tweet without `quoted_tweet_id` | `TweetData` with no such field | returns `None` |
| `quoted_tweet_id` is empty string | `quoted_tweet_id=""` | returns `None` |
| Tweet with `referenced_tweets` type `"replied_to"` only | no `quoted_tweet_id` mapped | returns `None` |

### `tests/test_api.py` additions (3 tests)

| Test | Input | Expected |
|---|---|---|
| `referenced_tweets` contains `type="quoted"` | `[{"type": "quoted", "id": "9876"}]` | `tweet_data["quoted_tweet_id"] == "9876"` |
| `referenced_tweets` contains only `type="replied_to"` | `[{"type": "replied_to", "id": "9876"}]` | `"quoted_tweet_id"` not in result |
| No `referenced_tweets` field | `{}` | `"quoted_tweet_id"` not in result |

All tests are mocked — no real API calls.

---

## Integration points

**Consumed by:** Phase 8 orchestrator  
- Calls `extract_quoted_tweet_id(tweet_data)` for every tweet in the processing loop  
- Owns depth tracking, API fetch of the quoted tweet, and all downstream processing

**Depends on:**  
- `api/types.TweetData` (read-only access to `quoted_tweet_id` field)  
- `bookmark_downloader.utils.logger` for DEBUG logging  
- Indirectly: the `twitter_client.py` fix that populates `quoted_tweet_id` in `TweetData`
