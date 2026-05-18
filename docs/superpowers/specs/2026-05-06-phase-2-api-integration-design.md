# Phase 2: API Integration — Design Spec

**Date:** 2026-05-06
**Status:** Retroactive — written to verify existing implementation
**Depends on:** Phase 1 (Config)

---

## Goal

Provide a library-agnostic X API client that fetches bookmarks, retrieves individual tweet details, extracts media URLs, and manages rate limit state. Produces the data structures that all later phases consume, but defers retry logic, storage, and processing to later phases.

---

## Scope

**In scope:**
- `src/bookmark_downloader/api/__init__.py` — empty package marker
- `src/bookmark_downloader/api/auth.py` — bearer token loading and header construction
- `src/bookmark_downloader/api/twitter_client.py` — API wrapper, TypedDict definitions, error types
- `tests/test_api.py` — unit tests (all network calls mocked)

**Out of scope:** OAuth 2.0 PKCE, token storage/encryption, retry-on-failure logic (Phase 7), any HTTP library choice.

---

## Architecture

### File Map

| File | Responsibility |
|------|----------------|
| `api/auth.py` | Load bearer token from Config; construct auth headers |
| `api/twitter_client.py` | X API wrapper — bookmarks, tweet lookup, media extraction, rate limit state. Also owns all TypedDicts and error types |
| `tests/test_api.py` | Unit tests for both modules; all HTTP responses mocked |

---

## Type Definitions

All TypedDicts are defined in `twitter_client.py`. They model the X API v2 response shape.

```python
from typing import Dict, List, Optional
from typing_extensions import NotRequired, TypedDict

class MediaVariant(TypedDict):
    content_type: str
    url: str
    bit_rate: NotRequired[int]

class MediaData(TypedDict):
    media_key: str
    type: str                                    # "photo", "video", "animated_gif"
    url: NotRequired[str]                        # photos only
    variants: NotRequired[List[MediaVariant]]    # videos and animated_gifs
    preview_image_url: NotRequired[str]

class AttachmentsData(TypedDict):
    media_keys: NotRequired[List[str]]

class ReferencedTweetData(TypedDict):
    type: str    # "quoted", "retweeted", "replied_to"
    id: str

class TweetData(TypedDict):
    id: str
    text: str
    author_id: str
    created_at: NotRequired[str]
    attachments: NotRequired[AttachmentsData]
    referenced_tweets: NotRequired[List[ReferencedTweetData]]

class UserData(TypedDict):
    id: str
    username: str
    name: str

class IncludesData(TypedDict):
    media: NotRequired[List[MediaData]]
    users: NotRequired[List[UserData]]
    tweets: NotRequired[List[TweetData]]    # expanded referenced tweets

class BookmarksResponse(TypedDict):
    tweets: List[TweetData]
    includes: IncludesData
    next_token: Optional[str]

class MediaUrl(TypedDict):
    url: str
    type: str       # "photo", "video", "animated_gif"
    media_key: str
```

---

## `auth.py`

### `TwitterAuth` class

```python
class TwitterAuth:
    def __init__(self, config: Config) -> None
```

- Reads `config["twitter"]["bearer_token"]` on construction
- Raises `ValueError` if the token is `None` or the placeholder string `"${TWITTER_BEARER_TOKEN}"`

```python
def get_bearer_token(self) -> str
```
Returns the bearer token string.

```python
def get_headers(self) -> Dict[str, str]
```
Returns the HTTP headers dict required to authenticate requests:
```python
{"Authorization": f"Bearer {token}"}
```

No other public methods. No network calls. No token refresh.

---

## `twitter_client.py`

### Error types

```python
class TwitterAPIError(Exception):
    def __init__(self, message: str, status_code: int) -> None
```
- `status_code` attribute is accessible after construction
- Base class for all X API errors

```python
class RateLimitError(TwitterAPIError):
    def __init__(self, reset_at: Optional[int] = None) -> None
```
- Subclass of `TwitterAPIError`
- `reset_at`: Unix timestamp from `X-RateLimit-Reset` response header, or `None` if unavailable
- Raised on HTTP 429

---

### `TwitterClient` class

```python
class TwitterClient:
    def __init__(self, config: Config) -> None
```
- Creates a `TwitterAuth` instance internally from `config`
- Reads request timeout from `config["twitter"]["request_timeout"]`
- Stores the last rate limit reset timestamp seen in any response header

---

#### `get_bookmarks`

```python
def get_bookmarks(
    self,
    user_id: str,
    max_results: int = 100,
    pagination_token: Optional[str] = None,
) -> BookmarksResponse
```

- Fetches one page of bookmarks for `user_id`
- Always requests these expansions: `attachments.media_keys`, `author_id`, `referenced_tweets.id`
- Always requests these fields:
  - tweet fields: `id`, `text`, `author_id`, `created_at`, `attachments`, `referenced_tweets`
  - media fields: `media_key`, `type`, `url`, `variants`, `preview_image_url`
  - user fields: `id`, `username`, `name`
- Returns `BookmarksResponse` with `next_token: None` when no further pages exist
- Raises `RateLimitError` on HTTP 429
- Raises `TwitterAPIError` on any other non-2xx response

---

#### `get_tweet_details`

```python
def get_tweet_details(
    self,
    tweet_id: str,
) -> Optional[TweetData]
```

- Fetches a single tweet by ID with the same expansions and fields as `get_bookmarks`
- Returns `None` if the tweet is not found (HTTP 404)
- Raises `RateLimitError` on HTTP 429
- Raises `TwitterAPIError` on any other non-2xx response

---

#### `get_me`

```python
def get_me(self) -> UserData
```

- Returns the authenticated user's `id`, `username`, and `name`
- Used by callers to obtain the `user_id` required by `get_bookmarks`
- Raises `TwitterAPIError` on failure

---

#### `is_rate_limited`

```python
def is_rate_limited(self) -> bool
```

- Returns `True` if the most recent API response was HTTP 429
- Returns `False` otherwise
- Resets to `False` after any successful (2xx) response

---

#### `wait_for_rate_limit_reset`

```python
def wait_for_rate_limit_reset(self) -> None
```

- Blocks until the rate limit window resets, using the `reset_at` timestamp stored from the last `RateLimitError`
- If no reset timestamp is available, waits 900 seconds (15 minutes)
- Logs the wait duration before sleeping

---

#### `extract_media_urls`

```python
@staticmethod
def extract_media_urls(
    tweet_data: TweetData,
    includes: IncludesData,
) -> List[MediaUrl]
```

- Cross-references `tweet_data["attachments"]["media_keys"]` against `includes["media"]`
- For `"photo"` type: uses the `url` field directly
- For `"video"` and `"animated_gif"` type: selects the variant with the highest `bit_rate` from `variants`
- Returns an empty list if the tweet has no `attachments`, no `media_keys`, or no matching entries in `includes["media"]`
- Preserves the order of `media_keys` in the output list

---

## Testing Strategy

All tests in `tests/test_api.py`. No real network calls — all HTTP responses mocked. No real filesystem writes.

### Required test classes and methods

| Class | Required tests |
|-------|----------------|
| `TestTwitterAuth` | `test_loads_bearer_token_from_config`, `test_get_headers_returns_authorization_header`, `test_raises_if_token_is_none`, `test_raises_if_token_is_placeholder` |
| `TestGetBookmarks` | `test_returns_tweet_list`, `test_pagination_token_passed_when_provided`, `test_next_token_none_on_last_page`, `test_includes_media_in_response`, `test_includes_users_in_response`, `test_raises_rate_limit_error_on_429`, `test_raises_api_error_on_non_2xx` |
| `TestGetTweetDetails` | `test_returns_tweet_data`, `test_returns_none_on_404`, `test_raises_rate_limit_error_on_429` |
| `TestGetMe` | `test_returns_user_data` |
| `TestExtractMediaUrls` | `test_photo_url_extracted`, `test_video_selects_highest_bitrate_variant`, `test_animated_gif_extracted`, `test_returns_empty_list_when_no_attachments`, `test_returns_empty_list_when_no_media_in_includes`, `test_preserves_media_key_order` |
| `TestRateLimit` | `test_is_rate_limited_false_by_default`, `test_is_rate_limited_true_after_429`, `test_is_rate_limited_false_after_success`, `test_wait_for_rate_limit_reset_sleeps_until_reset`, `test_wait_uses_default_900s_when_no_reset_timestamp` |
