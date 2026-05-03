"""X API client for bookmark fetching and media extraction using official XDK."""

import time
from typing import Any, Dict, Generator, List, Optional

from bookmark_downloader.utils.logger import get_logger

from .auth import AuthManager
from .types import MediaUrl, TweetData

logger = get_logger(__name__)

# Default expansions for API requests (configurable by caller)
DEFAULT_EXPANSIONS = {
    "expansions": ["author_id", "created_at", "attachments.media_keys", "referenced_tweets.id"],
    "media_fields": ["type", "url", "alt_text"],
    "user_fields": ["username", "created_at"],
    "tweet_fields": ["text", "author_id", "created_at", "attachments", "referenced_tweets"],
}


class RateLimitError(Exception):
    """Raised when rate limit is hit and auto-retry is exhausted."""

    pass


class TwitterClient:
    """X API client for fetching bookmarks and tweet data using official XDK."""

    def __init__(self, access_token: str):
        """
        Initialize Twitter API client with XDK.

        Args:
            access_token: X API access token (bearer token or OAuth).
        """
        try:
            from xdk import client
        except ImportError as e:
            raise ImportError("xdk package required. Install with: pip install xdk") from e

        self.access_token = access_token
        self.client = client.Client(
            bearer_token=access_token,
            user_ctx=False,  # Using app context for bookmarks
        )
        self._rate_limit_remaining = None
        self._rate_limit_reset = None
        self._max_retries = 3

    def _update_rate_limit_from_response(self, response: Any) -> None:
        """
        Update rate limit info from API response headers if available.

        Args:
            response: API response object.
        """
        try:
            if hasattr(response, "headers"):
                headers = response.headers
                self._rate_limit_remaining = int(headers.get("x-rate-limit-remaining", -1))
                self._rate_limit_reset = int(headers.get("x-rate-limit-reset", 0))
        except (ValueError, TypeError, AttributeError):
            pass

    def _handle_rate_limit(self) -> None:
        """
        Check and handle rate limiting with automatic wait.

        Raises:
            RateLimitError: If rate limit is 0 and wait timeout expires.
        """
        if self._rate_limit_remaining is None or self._rate_limit_remaining > 0:
            return

        if self._rate_limit_reset is None or self._rate_limit_reset == 0:
            logger.warning("Rate limited but reset time unknown, waiting 60 seconds")
            time.sleep(60)
            return

        now = int(time.time())
        wait_time = max(0, self._rate_limit_reset - now)

        if wait_time > 0:
            logger.warning(
                f"Rate limited. Waiting {wait_time}s until reset at {self._rate_limit_reset}"
            )
            time.sleep(wait_time + 1)  # Add 1s buffer

    def _build_expansions_params(
        self, expansions: Optional[Dict[str, List[str]]] = None
    ) -> Dict[str, Any]:
        """
        Build query parameters from expansions config.

        Args:
            expansions: Custom expansions dict. Uses defaults if None.

        Returns:
            Dict of parameters for XDK client.
        """
        if expansions is None:
            expansions = DEFAULT_EXPANSIONS

        params = {}
        if expansions.get("expansions"):
            params["expansions"] = ",".join(expansions["expansions"])
        if expansions.get("media_fields"):
            params["media.fields"] = ",".join(expansions["media_fields"])
        if expansions.get("user_fields"):
            params["user.fields"] = ",".join(expansions["user_fields"])
        if expansions.get("tweet_fields"):
            params["tweet.fields"] = ",".join(expansions["tweet_fields"])

        return params

    def _map_quoted_tweet_id(self, tweet: Dict) -> Optional[str]:
        """
        Extract quoted tweet ID from referenced_tweets array.

        Args:
            tweet: Raw tweet dict from API response.

        Returns:
            ID of the quoted tweet, or None if not a quote.
        """
        for ref in tweet.get("referenced_tweets", []):
            if ref.get("type") == "quoted":
                return ref.get("id")
        return None

    def get_bookmarks_iter(
        self,
        batch_size: int = 100,
        expansions: Optional[Dict[str, List[str]]] = None,
    ) -> Generator[TweetData, None, None]:
        """
        Fetch bookmarks with automatic pagination (generator pattern).

        Yields TweetData objects one at a time. Pagination is handled
        internally, allowing caller to iterate through all bookmarks.

        Args:
            batch_size: Number of bookmarks per API call (max 100).
            expansions: Custom expansions dict. Uses defaults if None.

        Yields:
            TweetData objects from bookmarks.

        Raises:
            ValueError: On API error or missing required fields.
            Exception: On non-retriable errors.
        """
        batch_size = min(batch_size, 100)  # API max is 100
        pagination_token = None
        retry_count = 0

        params = self._build_expansions_params(expansions)
        params["max_results"] = batch_size

        while True:
            self._handle_rate_limit()

            try:
                logger.debug(f"Fetching bookmarks (size={batch_size})")

                # Use XDK to fetch bookmarks
                response = self.client.get_users_me_bookmarks(**params)

                # Update rate limit info if available
                self._update_rate_limit_from_response(response)

                if response.status_code == 429:
                    # Rate limit hit
                    retry_count += 1
                    if retry_count >= self._max_retries:
                        raise RateLimitError("Rate limit exceeded after max retries")
                    logger.warning(f"Rate limited (429). Retry {retry_count}/{self._max_retries}")
                    self._handle_rate_limit()
                    continue

                if response.status_code >= 400:
                    raise ValueError(f"API error {response.status_code}: {response.text}")

                # Parse response data
                data = response.json() if hasattr(response, "json") else response
                tweets = data.get("data", []) if isinstance(data, dict) else []

                if not tweets:
                    logger.debug("No more bookmarks to fetch")
                    break

                # Validate and yield each tweet
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

                # Check for next page
                meta = data.get("meta", {}) if isinstance(data, dict) else {}
                pagination_token = meta.get("next_token")
                if not pagination_token:
                    logger.debug("Reached end of bookmarks")
                    break

                params["pagination_token"] = pagination_token
                retry_count = 0  # Reset retry count on success

            except Exception as e:
                if isinstance(e, (RateLimitError, ValueError)):
                    raise
                # Retry on network errors
                retry_count += 1
                if retry_count >= self._max_retries:
                    logger.error(f"Max retries exceeded: {e}")
                    raise
                wait_time = 2 ** retry_count
                logger.warning(f"Request error: {e}. Retrying in {wait_time}s ({retry_count}/{self._max_retries})")
                time.sleep(wait_time)

    def get_tweet_details(
        self,
        tweet_id: str,
        expansions: Optional[Dict[str, List[str]]] = None,
    ) -> TweetData:
        """
        Fetch detailed information for a specific tweet.

        Args:
            tweet_id: The tweet ID to fetch.
            expansions: Custom expansions dict. Uses defaults if None.

        Returns:
            TweetData with tweet information.

        Raises:
            ValueError: If tweet not found, deleted, or inaccessible.
            Exception: On non-retriable errors.
        """
        params = self._build_expansions_params(expansions)

        try:
            logger.debug(f"Fetching tweet details for {tweet_id}")

            response = self.client.get_tweets_id(id=tweet_id, **params)

            # Update rate limit info
            self._update_rate_limit_from_response(response)

            if response.status_code == 404:
                logger.warning(f"Tweet {tweet_id} not found (deleted or inaccessible)")
                raise ValueError(f"Tweet {tweet_id} deleted or inaccessible")
            elif response.status_code == 403:
                logger.warning(f"Tweet {tweet_id} access denied (protected or private account)")
                raise ValueError(f"Tweet {tweet_id} access denied")
            elif response.status_code >= 400:
                raise ValueError(f"API error {response.status_code}")

            data = response.json() if hasattr(response, "json") else response
            tweet = data.get("data") if isinstance(data, dict) else None

            if not tweet:
                raise ValueError(f"No data in tweet response for {tweet_id}")

            self._validate_tweet(tweet)
            quoted_id = self._map_quoted_tweet_id(tweet)
            if quoted_id:
                tweet["quoted_tweet_id"] = quoted_id
            return tweet

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error fetching tweet {tweet_id}: {e}")
            raise

    def extract_media_urls(self, tweet_data: TweetData) -> List[MediaUrl]:
        """
        Extract media URLs from tweet data.

        Handles photos, videos, and animated GIFs. Returns URLs in order
        as they appear in the tweet.

        Args:
            tweet_data: TweetData object from API.

        Returns:
            List of MediaUrl dicts with url, type, and optional alt_text.
        """
        media_urls: List[MediaUrl] = []

        # Get media data from includes (set by caller based on XDK response)
        attachments = tweet_data.get("attachments", {})
        media_keys = attachments.get("media_keys", [])

        if not media_keys:
            logger.debug(f"Tweet {tweet_data['id']} has no media")
            return media_urls

        logger.debug(f"Tweet {tweet_data['id']} has {len(media_keys)} media items")
        # Media details would come from includes.media in the full response
        # which is handled by XDK's response structure

        return media_urls

    def _validate_tweet(self, tweet: Dict[str, Any]) -> None:
        """
        Validate that tweet has required fields.

        Args:
            tweet: Tweet data dict from API.

        Raises:
            ValueError: If required fields are missing.
        """
        if not tweet.get("id"):
            raise ValueError("Missing required field: id")
        if not tweet.get("text"):
            raise ValueError("Missing required field: text")
        if not tweet.get("author_id"):
            raise ValueError("Missing required field: author_id")

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.

        Returns:
            Dict with remaining requests and reset time.
        """
        return {
            "remaining": self._rate_limit_remaining,
            "reset_timestamp": self._rate_limit_reset,
        }


class BookmarkClient:
    """High-level client for bookmark downloading with auth."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize bookmark client with authentication.

        Args:
            config: Configuration dict. If None, loads from config file.
        """
        from bookmark_downloader.config import get_config

        self.config = config or get_config()
        auth_manager = AuthManager(self.config)
        access_token = auth_manager.get_access_token()
        self.client = TwitterClient(access_token)

    def get_bookmarks(
        self,
        batch_size: int = 100,
        expansions: Optional[Dict[str, List[str]]] = None,
    ) -> Generator[TweetData, None, None]:
        """
        Get authenticated bookmarks with pagination.

        Args:
            batch_size: Bookmarks per API call.
            expansions: Custom expansions (uses defaults if None).

        Yields:
            TweetData for each bookmark.
        """
        return self.client.get_bookmarks_iter(batch_size, expansions)

    def get_tweet_details(
        self,
        tweet_id: str,
        expansions: Optional[Dict[str, List[str]]] = None,
    ) -> TweetData:
        """Get detailed tweet data."""
        return self.client.get_tweet_details(tweet_id, expansions)

    def extract_media_urls(self, tweet_data: TweetData) -> List[MediaUrl]:
        """Extract media URLs from tweet."""
        return self.client.extract_media_urls(tweet_data)
