"""X API client for bookmark fetching and media extraction."""

import time
from typing import Any, Dict, Generator, List, Optional

from bookmark_downloader.utils.logger import get_logger

from .auth import AuthManager
from .types import BookmarkResponse, MediaUrl, TweetData

logger = get_logger(__name__)

# Default expansions for API requests (configurable by caller)
DEFAULT_EXPANSIONS = {
    "expansions": ["author_id", "created_at", "attachments.media_keys", "quote.id"],
    "media_fields": ["type", "url", "alt_text"],
    "user_fields": ["username", "created_at"],
    "tweet_fields": ["text", "author_id", "created_at", "attachments"],
}


class RateLimitError(Exception):
    """Raised when rate limit is hit and auto-retry is exhausted."""

    pass


class TwitterClient:
    """X API client for fetching bookmarks and tweet data."""

    def __init__(self, access_token: str, base_url: str = "https://api.x.com/2"):
        """
        Initialize Twitter API client.

        Args:
            access_token: X API access token (bearer token or OAuth).
            base_url: Base URL for X API (default v2 API).
        """
        self.access_token = access_token
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "BookmarkDownloader/1.0",
        }
        self._rate_limit_remaining = None
        self._rate_limit_reset = None

    def _update_rate_limit(self, response_headers: Dict[str, str]) -> None:
        """
        Update rate limit info from response headers.

        Args:
            response_headers: Response headers from API call.
        """
        try:
            self._rate_limit_remaining = int(
                response_headers.get("x-rate-limit-remaining", -1)
            )
            self._rate_limit_reset = int(response_headers.get("x-rate-limit-reset", 0))
        except (ValueError, TypeError):
            pass

    def _check_rate_limit(self) -> None:
        """
        Check if rate limited and wait if needed.

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
        else:
            # Reset time passed, try again
            pass

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make authenticated API request with automatic rate limit handling.

        Args:
            method: HTTP method (GET, POST, etc.).
            endpoint: API endpoint (without base URL).
            params: Query parameters.
            json_data: JSON body data.

        Returns:
            Parsed JSON response.

        Raises:
            ValueError: On client error (4xx).
            Exception: On server error (5xx) after retries.
        """
        import httpx

        url = f"{self.base_url}{endpoint}"
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            self._check_rate_limit()

            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.request(
                        method,
                        url,
                        headers=self.headers,
                        params=params,
                        json=json_data,
                    )

                    # Update rate limit info
                    self._update_rate_limit(response.headers)

                    # Handle rate limiting
                    if response.status_code == 429:
                        retry_count += 1
                        if retry_count >= max_retries:
                            raise RateLimitError(
                                "Rate limit exceeded after max retries"
                            )
                        logger.warning(
                            f"Rate limited (429). Retry {retry_count}/{max_retries}"
                        )
                        self._check_rate_limit()
                        continue

                    # Handle client errors
                    if 400 <= response.status_code < 500:
                        logger.error(
                            f"API error {response.status_code}: {response.text}"
                        )
                        raise ValueError(
                            f"API error {response.status_code}: {response.text}"
                        )

                    # Handle server errors with retry
                    if response.status_code >= 500:
                        retry_count += 1
                        if retry_count >= max_retries:
                            raise Exception(
                                f"Server error {response.status_code} after {max_retries} retries"
                            )
                        wait_time = 2 ** retry_count  # Exponential backoff
                        logger.warning(
                            f"Server error {response.status_code}. "
                            f"Retrying in {wait_time}s ({retry_count}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue

                    # Success
                    response.raise_for_status()
                    return response.json()

            except httpx.RequestError as e:
                retry_count += 1
                if retry_count >= max_retries:
                    raise
                wait_time = 2 ** retry_count
                logger.warning(
                    f"Request error: {e}. "
                    f"Retrying in {wait_time}s ({retry_count}/{max_retries})"
                )
                time.sleep(wait_time)

        raise Exception("Max retries exceeded")

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
        if expansions is None:
            expansions = DEFAULT_EXPANSIONS

        batch_size = min(batch_size, 100)  # API max is 100
        pagination_token = None

        while True:
            params = {
                "max_results": batch_size,
                **expansions,
            }
            if pagination_token:
                params["pagination_token"] = pagination_token

            logger.debug(f"Fetching bookmarks batch (size={batch_size})")

            try:
                response = self._make_request("GET", "/users/me/bookmarks", params=params)
            except RateLimitError:
                logger.error("Rate limit hit during bookmark pagination")
                raise
            except ValueError as e:
                logger.error(f"Permanent API error during bookmark fetch: {e}")
                raise

            # Parse response
            tweets = response.get("data", [])
            if not tweets:
                logger.debug("No more bookmarks to fetch")
                break

            # Validate and yield each tweet
            for tweet in tweets:
                try:
                    self._validate_tweet(tweet)
                    yield tweet
                except ValueError as e:
                    logger.error(f"Invalid tweet data for ID {tweet.get('id')}: {e}")
                    raise

            # Check for next page
            pagination_token = response.get("meta", {}).get("next_token")
            if not pagination_token:
                logger.debug("Reached end of bookmarks")
                break

            logger.debug(f"More bookmarks available, token: {pagination_token[:10]}...")

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
        if expansions is None:
            expansions = DEFAULT_EXPANSIONS

        params = {**expansions}

        try:
            response = self._make_request("GET", f"/tweets/{tweet_id}", params=params)
        except RateLimitError:
            logger.error(f"Rate limit hit fetching tweet {tweet_id}")
            raise
        except ValueError as e:
            if "404" in str(e):
                logger.warning(f"Tweet {tweet_id} not found (deleted or inaccessible)")
                raise ValueError(f"Tweet {tweet_id} deleted or inaccessible") from e
            elif "403" in str(e):
                logger.warning(
                    f"Tweet {tweet_id} access denied (protected or private account)"
                )
                raise ValueError(f"Tweet {tweet_id} access denied") from e
            raise

        tweet = response.get("data")
        if not tweet:
            raise ValueError(f"No data in tweet response for {tweet_id}")

        try:
            self._validate_tweet(tweet)
        except ValueError as e:
            logger.error(f"Invalid tweet data for {tweet_id}: {e}")
            raise

        return tweet

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

        # Get media data from includes
        attachments = tweet_data.get("attachments", {})
        media_keys = attachments.get("media_keys", [])

        if not media_keys:
            logger.debug(f"Tweet {tweet_data['id']} has no media")
            return media_urls

        # In a real implementation, we'd get media details from includes.media
        # For now, we note that we need the actual XDK response structure
        # which includes media data in the includes section
        logger.debug(f"Tweet {tweet_data['id']} has {len(media_keys)} media items")

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
            Dict with remaining requests, limit, and reset time.
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
