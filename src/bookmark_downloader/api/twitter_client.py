"""X API client for bookmark fetching and media extraction using official XDK."""

import time
from typing import Dict, List, Optional

from typing_extensions import NotRequired, TypedDict

from bookmark_downloader.config import Config
from bookmark_downloader.utils.logger import get_logger

from .auth import TwitterAuth

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# TypedDicts
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TwitterAPIError(Exception):
    """Base class for all X API errors."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class RateLimitError(TwitterAPIError):
    """Raised on HTTP 429 – rate limit exceeded."""

    def __init__(self, reset_at: Optional[int] = None) -> None:
        super().__init__("Rate limit exceeded", status_code=429)
        self.reset_at = reset_at


# ---------------------------------------------------------------------------
# TwitterClient
# ---------------------------------------------------------------------------

# Fields/expansions always requested
_EXPANSIONS = "attachments.media_keys,author_id,referenced_tweets.id"
_TWEET_FIELDS = "id,text,author_id,created_at,attachments,referenced_tweets"
_MEDIA_FIELDS = "media_key,type,url,variants,preview_image_url"
_USER_FIELDS = "id,username,name"


class TwitterClient:
    """X API client for fetching bookmarks and tweet data using official XDK."""

    def __init__(self, config: Config) -> None:
        """
        Initialize Twitter API client.

        Creates a TwitterAuth instance internally from config.

        Args:
            config: Application configuration object.
        """
        try:
            from xdk import client as xdk_client
        except ImportError as e:
            raise ImportError("xdk package required. Install with: pip install xdk") from e

        auth = TwitterAuth(config)
        bearer_token = auth.get_bearer_token()

        self._client = xdk_client.Client(
            bearer_token=bearer_token,
        )
        self._is_rate_limited: bool = False
        self._rate_limit_reset: Optional[int] = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_reset_header(self, response) -> Optional[int]:  # type: ignore[type-arg]
        """Return the X-RateLimit-Reset header value as an int, or None."""
        try:
            return int(response.headers.get("X-RateLimit-Reset", ""))
        except (ValueError, TypeError):
            return None

    def _update_rate_limit_headers(self, response) -> None:  # type: ignore[type-arg]
        """Read X-RateLimit-* headers from a response and update internal state."""
        reset = self._parse_reset_header(response)
        if reset is not None:
            self._rate_limit_reset = reset

    def _raise_for_status(self, response) -> None:  # type: ignore[type-arg]
        """Raise TwitterAPIError subclasses for non-2xx responses."""
        status = response.status_code
        if status == 429:
            self._is_rate_limited = True
            reset_at = self._parse_reset_header(response)
            if reset_at is not None:
                self._rate_limit_reset = reset_at
            raise RateLimitError(reset_at=reset_at)
        if status >= 400:
            raise TwitterAPIError(
                f"API error {status}: {getattr(response, 'text', '')}",
                status_code=status,
            )
        # 2xx – clear rate-limited flag
        self._is_rate_limited = False
        self._update_rate_limit_headers(response)

    @staticmethod
    def _parse_bookmarks_response(raw: dict) -> BookmarksResponse:  # type: ignore[type-arg]
        """Convert raw API JSON to BookmarksResponse TypedDict."""
        tweets: List[TweetData] = raw.get("data", [])
        raw_includes = raw.get("includes", {})
        includes: IncludesData = {}
        if "media" in raw_includes:
            includes["media"] = raw_includes["media"]
        if "users" in raw_includes:
            includes["users"] = raw_includes["users"]
        if "tweets" in raw_includes:
            includes["tweets"] = raw_includes["tweets"]
        meta = raw.get("meta", {})
        next_token: Optional[str] = meta.get("next_token")
        return BookmarksResponse(tweets=tweets, includes=includes, next_token=next_token)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_bookmarks(
        self,
        user_id: str,
        max_results: int = 100,
        pagination_token: Optional[str] = None,
    ) -> BookmarksResponse:
        """
        Fetch one page of bookmarks for user_id.

        Args:
            user_id: The authenticated user's ID.
            max_results: Number of results to return (max 100).
            pagination_token: Token for the next page, or None for first page.

        Returns:
            BookmarksResponse with tweets, includes, and next_token.

        Raises:
            RateLimitError: On HTTP 429.
            TwitterAPIError: On any other non-2xx response.
        """
        params: Dict[str, object] = {
            "expansions": _EXPANSIONS,
            "tweet.fields": _TWEET_FIELDS,
            "media.fields": _MEDIA_FIELDS,
            "user.fields": _USER_FIELDS,
            "max_results": max_results,
        }
        if pagination_token is not None:
            params["pagination_token"] = pagination_token

        response = self._client.get_users_id_bookmarks(id=user_id, **params)
        self._raise_for_status(response)

        raw = response.json() if hasattr(response, "json") else response
        return self._parse_bookmarks_response(raw if isinstance(raw, dict) else {})

    def get_tweet_details(
        self,
        tweet_id: str,
    ) -> Optional[TweetData]:
        """
        Fetch a single tweet by ID.

        Args:
            tweet_id: The tweet ID to fetch.

        Returns:
            TweetData dict, or None if tweet not found (HTTP 404).

        Raises:
            RateLimitError: On HTTP 429.
            TwitterAPIError: On any other non-2xx response.
        """
        params: Dict[str, object] = {
            "expansions": _EXPANSIONS,
            "tweet.fields": _TWEET_FIELDS,
            "media.fields": _MEDIA_FIELDS,
            "user.fields": _USER_FIELDS,
        }

        response = self._client.get_tweets_id(id=tweet_id, **params)

        if response.status_code == 404:
            self._is_rate_limited = False
            return None

        self._raise_for_status(response)

        raw = response.json() if hasattr(response, "json") else response
        if isinstance(raw, dict):
            return raw.get("data")
        return None

    def get_me(self) -> UserData:
        """
        Return authenticated user's id, username, name.

        Raises:
            TwitterAPIError: On failure.
        """
        params: Dict[str, object] = {
            "user.fields": _USER_FIELDS,
        }
        response = self._client.get_users_me(**params)
        self._raise_for_status(response)

        raw = response.json() if hasattr(response, "json") else response
        if isinstance(raw, dict):
            return raw.get("data", {})
        return {}  # type: ignore[return-value]

    def is_rate_limited(self) -> bool:
        """
        Return True if the most recent API response was HTTP 429.

        Resets to False after any successful (2xx) response.
        """
        return self._is_rate_limited

    def wait_for_rate_limit_reset(self) -> None:
        """
        Block until the rate limit window resets.

        Uses the reset_at timestamp stored from the last RateLimitError.
        Falls back to 900 seconds if no timestamp is available.
        Logs the wait duration before sleeping.
        """
        if self._rate_limit_reset is not None:
            now = int(time.time())
            wait_seconds = max(0, self._rate_limit_reset - now)
        else:
            wait_seconds = 900

        logger.info(f"Rate limited — waiting {wait_seconds}s for reset")
        time.sleep(wait_seconds)

    @staticmethod
    def extract_media_urls(
        tweet_data: TweetData,
        includes: IncludesData,
    ) -> List[MediaUrl]:
        """
        Extract media URLs from tweet_data by cross-referencing includes["media"].

        For "photo" type: uses url field directly.
        For "video" and "animated_gif": selects variant with highest bit_rate.
        Preserves the order of media_keys.

        Args:
            tweet_data: A single TweetData object.
            includes: The IncludesData from the same API response.

        Returns:
            List of MediaUrl dicts (may be empty).
        """
        attachments = tweet_data.get("attachments") or {}
        media_keys: List[str] = attachments.get("media_keys") or []

        if not media_keys:
            return []

        media_by_key: Dict[str, MediaData] = {
            m["media_key"]: m for m in (includes.get("media") or [])
        }

        results: List[MediaUrl] = []
        for key in media_keys:
            media = media_by_key.get(key)
            if media is None:
                continue

            media_type = media["type"]

            if media_type == "photo":
                url = media.get("url")
                if url:
                    results.append(MediaUrl(url=url, type=media_type, media_key=key))

            elif media_type in ("video", "animated_gif"):
                variants: List[MediaVariant] = media.get("variants") or []
                best = max(
                    (v for v in variants if "bit_rate" in v),
                    key=lambda v: v["bit_rate"],  # type: ignore[typeddict-item]
                    default=None,
                )
                if best is None and variants:
                    best = variants[0]
                if best:
                    results.append(MediaUrl(url=best["url"], type=media_type, media_key=key))

        return results

    def _map_quoted_tweet_id(self, tweet: dict) -> Optional[str]:
        """Return the quoted tweet ID from referenced_tweets, or None."""
        for ref in tweet.get("referenced_tweets", []):
            if ref.get("type") == "quoted":
                return ref.get("id")
        return None
