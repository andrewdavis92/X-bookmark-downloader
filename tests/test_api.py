"""Tests for X API client using official XDK."""

import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from bookmark_downloader.api.auth import AuthManager, OAuth2PKCE, TokenStore
from bookmark_downloader.api.twitter_client import (
    BookmarksResponse,
    IncludesData,
    MediaData,
    MediaUrl,
    MediaVariant,
    RateLimitError,
    TweetData,
    TwitterAPIError,
    TwitterClient,
    UserData,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(bearer_token: str = "test_bearer_token") -> dict:
    """Return a minimal config dict accepted by TwitterClient."""
    return {
        "twitter": {
            "bearer_token": bearer_token,
            "request_timeout": 30,
        },
        "paths": {
            "logs_directory": "/tmp",
        },
    }


def _make_client(bearer_token: str = "test_bearer_token") -> TwitterClient:
    """Create a TwitterClient with all external dependencies patched."""
    config = _make_config(bearer_token)
    with patch("xdk.client.Client"):
        with patch(
            "bookmark_downloader.api.twitter_client.TwitterAuth"
        ) as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.get_bearer_token.return_value = bearer_token
            mock_auth_cls.return_value = mock_auth
            return TwitterClient(config)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tweet() -> TweetData:
    """Sample tweet data from API."""
    return {
        "id": "1234567890",
        "text": "This is a test tweet",
        "author_id": "user123",
        "created_at": "2024-04-04T10:00:00Z",
        "attachments": {"media_keys": ["7_1234567890"]},
    }


@pytest.fixture
def sample_tweet_no_media() -> TweetData:
    """Sample text-only tweet."""
    return {
        "id": "9876543210",
        "text": "Text only tweet",
        "author_id": "user456",
        "created_at": "2024-04-04T11:00:00Z",
    }


@pytest.fixture
def sample_bookmark_response(sample_tweet: TweetData) -> dict:
    """Sample bookmarks API response (raw JSON)."""
    return {
        "data": [sample_tweet],
        "meta": {"result_count": 1},
    }


@pytest.fixture
def sample_bookmark_response_paginated(sample_tweet: TweetData) -> dict:
    """Sample bookmarks response with next_token for pagination."""
    return {
        "data": [sample_tweet],
        "meta": {"result_count": 1, "next_token": "b26v89c19zqg8o3fpza0xpa6g55ombwfjhxbzrx4zzbe"},
    }


# ---------------------------------------------------------------------------
# TwitterClient initialisation
# ---------------------------------------------------------------------------


class TestTwitterClientInitialization:
    """Test TwitterClient initialization."""

    def test_client_init_creates_twitter_auth(self):
        """TwitterClient must create a TwitterAuth internally from config."""
        config = _make_config()
        with patch("xdk.client.Client") as mock_xdk:
            with patch(
                "bookmark_downloader.api.twitter_client.TwitterAuth"
            ) as mock_auth_cls:
                mock_auth = MagicMock()
                mock_auth.get_bearer_token.return_value = "test_bearer_token"
                mock_auth_cls.return_value = mock_auth

                client = TwitterClient(config)

                mock_auth_cls.assert_called_once_with(config)
                mock_auth.get_bearer_token.assert_called_once()
                mock_xdk.assert_called_once()

    def test_client_reads_request_timeout(self):
        """TwitterClient must read request_timeout from config."""
        config = _make_config()
        config["twitter"]["request_timeout"] = 45
        with patch("xdk.client.Client"):
            with patch(
                "bookmark_downloader.api.twitter_client.TwitterAuth"
            ) as mock_auth_cls:
                mock_auth = MagicMock()
                mock_auth.get_bearer_token.return_value = "tok"
                mock_auth_cls.return_value = mock_auth
                client = TwitterClient(config)

        assert client._timeout == 45

    def test_client_init_is_rate_limited_false(self):
        """is_rate_limited() must return False after initialization."""
        client = _make_client()
        assert client.is_rate_limited() is False


# ---------------------------------------------------------------------------
# get_bookmarks
# ---------------------------------------------------------------------------


class TestGetBookmarks:
    """Test get_bookmarks (single-page fetch)."""

    def test_get_bookmarks_single_page(self, sample_bookmark_response: dict):
        """Returns a BookmarksResponse with tweets and None next_token."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bookmark_response
        mock_response.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_response

        result = client.get_bookmarks(user_id="me")

        assert len(result["tweets"]) == 1
        assert result["tweets"][0]["id"] == "1234567890"
        assert result["next_token"] is None

    def test_get_bookmarks_with_pagination_token(self, sample_bookmark_response: dict):
        """Passes pagination_token to the underlying XDK call when provided."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bookmark_response
        mock_response.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_response

        client.get_bookmarks(user_id="me", pagination_token="tok123")

        call_kwargs = client._client.get_users_id_bookmarks.call_args[1]
        assert call_kwargs.get("pagination_token") == "tok123"

    def test_get_bookmarks_returns_next_token(self, sample_bookmark_response_paginated: dict):
        """next_token is populated when the API response contains one."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bookmark_response_paginated
        mock_response.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_response

        result = client.get_bookmarks(user_id="me")

        assert result["next_token"] == "b26v89c19zqg8o3fpza0xpa6g55ombwfjhxbzrx4zzbe"

    def test_get_bookmarks_raises_rate_limit_error(self):
        """RateLimitError is raised on HTTP 429."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_response

        with pytest.raises(RateLimitError):
            client.get_bookmarks(user_id="me")

    def test_get_bookmarks_raises_twitter_api_error(self):
        """TwitterAPIError is raised on other non-2xx responses."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_response

        with pytest.raises(TwitterAPIError) as exc_info:
            client.get_bookmarks(user_id="me")

        assert exc_info.value.status_code == 500

    def test_get_bookmarks_always_requests_required_fields(self):
        """get_bookmarks always sends the required expansions and fields."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [], "meta": {}}
        mock_response.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_response

        client.get_bookmarks(user_id="me")

        call_kwargs = client._client.get_users_id_bookmarks.call_args[1]
        assert "attachments.media_keys" in call_kwargs.get("expansions", "")
        assert "author_id" in call_kwargs.get("expansions", "")
        assert "referenced_tweets.id" in call_kwargs.get("expansions", "")
        assert "referenced_tweets" in call_kwargs.get("tweet.fields", "")
        assert "preview_image_url" in call_kwargs.get("media.fields", "")
        assert "variants" in call_kwargs.get("media.fields", "")


# ---------------------------------------------------------------------------
# get_tweet_details
# ---------------------------------------------------------------------------


class TestGetTweetDetails:
    """Test get_tweet_details."""

    def test_returns_tweet_data_on_200(self):
        """Returns TweetData on success."""
        client = _make_client()
        tweet = {"id": "123", "text": "hello", "author_id": "u1"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": tweet}
        mock_response.headers = {}
        client._client.get_tweets_id.return_value = mock_response

        result = client.get_tweet_details("123")

        assert result is not None
        assert result["id"] == "123"

    def test_returns_none_on_404(self):
        """Returns None when tweet not found (HTTP 404)."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {}
        client._client.get_tweets_id.return_value = mock_response

        result = client.get_tweet_details("deleted_tweet_id")

        assert result is None

    def test_raises_rate_limit_error_on_429(self):
        """RateLimitError raised on HTTP 429."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        client._client.get_tweets_id.return_value = mock_response

        with pytest.raises(RateLimitError):
            client.get_tweet_details("some_id")

    def test_raises_twitter_api_error_on_other_errors(self):
        """TwitterAPIError raised on other non-2xx."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.headers = {}
        client._client.get_tweets_id.return_value = mock_response

        with pytest.raises(TwitterAPIError) as exc_info:
            client.get_tweet_details("some_id")

        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# get_me
# ---------------------------------------------------------------------------


class TestGetMe:
    """Test get_me."""

    def test_returns_user_data(self):
        """get_me returns UserData on success."""
        client = _make_client()
        user = {"id": "u1", "username": "testuser", "name": "Test User"}
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": user}
        mock_response.headers = {}
        client._client.get_users_me.return_value = mock_response

        result = client.get_me()

        assert result["id"] == "u1"
        assert result["username"] == "testuser"
        assert result["name"] == "Test User"

    def test_raises_twitter_api_error_on_failure(self):
        """TwitterAPIError raised when get_me fails."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_response.headers = {}
        client._client.get_users_me.return_value = mock_response

        with pytest.raises(TwitterAPIError) as exc_info:
            client.get_me()

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# is_rate_limited
# ---------------------------------------------------------------------------


class TestIsRateLimited:
    """Test is_rate_limited flag behaviour."""

    def test_false_initially(self):
        """Starts as False."""
        client = _make_client()
        assert client.is_rate_limited() is False

    def test_true_after_429(self):
        """Becomes True after a 429 response."""
        client = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_response

        with pytest.raises(RateLimitError):
            client.get_bookmarks(user_id="me")

        assert client.is_rate_limited() is True

    def test_resets_to_false_after_2xx(self):
        """Resets to False after a successful 2xx response."""
        client = _make_client()

        # First trigger a 429
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_429
        with pytest.raises(RateLimitError):
            client.get_bookmarks(user_id="me")
        assert client.is_rate_limited() is True

        # Now succeed
        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"data": [], "meta": {}}
        mock_200.headers = {}
        client._client.get_users_id_bookmarks.return_value = mock_200
        client.get_bookmarks(user_id="me")
        assert client.is_rate_limited() is False


# ---------------------------------------------------------------------------
# wait_for_rate_limit_reset
# ---------------------------------------------------------------------------


class TestWaitForRateLimitReset:
    """Test wait_for_rate_limit_reset."""

    @patch("time.sleep")
    def test_waits_900s_when_no_reset_timestamp(self, mock_sleep: Mock):
        """Waits 900 seconds when no reset timestamp is available."""
        client = _make_client()
        client.wait_for_rate_limit_reset()
        mock_sleep.assert_called_once_with(900)

    @patch("time.sleep")
    @patch("time.time", return_value=1000)
    def test_waits_until_reset_timestamp(self, mock_time: Mock, mock_sleep: Mock):
        """Waits until the stored reset_at timestamp."""
        client = _make_client()
        client._rate_limit_reset = 1060  # 60 seconds from now (mock time=1000)
        client.wait_for_rate_limit_reset()
        mock_sleep.assert_called_once_with(60)

    @patch("time.sleep")
    def test_logs_before_sleeping(self, mock_sleep: Mock):
        """Logs the wait duration before sleeping (smoke test — no error thrown)."""
        client = _make_client()
        # Should not raise even without logger setup
        client.wait_for_rate_limit_reset()
        assert mock_sleep.called


# ---------------------------------------------------------------------------
# extract_media_urls (static method)
# ---------------------------------------------------------------------------


class TestExtractMediaUrls:
    """Test extract_media_urls static method."""

    def test_is_static_method(self):
        """extract_media_urls must be a static method."""
        assert isinstance(
            TwitterClient.__dict__["extract_media_urls"],
            staticmethod,
        )

    def test_returns_empty_for_no_attachments(self, sample_tweet_no_media: TweetData):
        """Returns empty list when tweet has no attachments."""
        includes: IncludesData = {}
        result = TwitterClient.extract_media_urls(sample_tweet_no_media, includes)
        assert result == []

    def test_returns_empty_when_media_key_not_in_includes(self, sample_tweet: TweetData):
        """Returns empty list when media_keys don't match any entry in includes."""
        includes: IncludesData = {"media": []}
        result = TwitterClient.extract_media_urls(sample_tweet, includes)
        assert result == []

    def test_extracts_photo_url(self):
        """Extracts url directly for photo type."""
        tweet: TweetData = {
            "id": "1",
            "text": "photo",
            "author_id": "u1",
            "attachments": {"media_keys": ["3_abc"]},
        }
        includes: IncludesData = {
            "media": [
                {"media_key": "3_abc", "type": "photo", "url": "https://example.com/photo.jpg"}
            ]
        }
        result = TwitterClient.extract_media_urls(tweet, includes)
        assert len(result) == 1
        assert result[0]["url"] == "https://example.com/photo.jpg"
        assert result[0]["type"] == "photo"
        assert result[0]["media_key"] == "3_abc"

    def test_extracts_video_highest_bitrate(self):
        """Selects variant with highest bit_rate for video type."""
        tweet: TweetData = {
            "id": "1",
            "text": "video",
            "author_id": "u1",
            "attachments": {"media_keys": ["7_abc"]},
        }
        includes: IncludesData = {
            "media": [
                {
                    "media_key": "7_abc",
                    "type": "video",
                    "variants": [
                        {"content_type": "video/mp4", "url": "https://low.mp4", "bit_rate": 256000},
                        {"content_type": "video/mp4", "url": "https://high.mp4", "bit_rate": 2176000},
                        {"content_type": "video/mp4", "url": "https://mid.mp4", "bit_rate": 832000},
                    ],
                }
            ]
        }
        result = TwitterClient.extract_media_urls(tweet, includes)
        assert len(result) == 1
        assert result[0]["url"] == "https://high.mp4"
        assert result[0]["type"] == "video"

    def test_extracts_animated_gif(self):
        """Extracts URL for animated_gif type."""
        tweet: TweetData = {
            "id": "1",
            "text": "gif",
            "author_id": "u1",
            "attachments": {"media_keys": ["16_abc"]},
        }
        includes: IncludesData = {
            "media": [
                {
                    "media_key": "16_abc",
                    "type": "animated_gif",
                    "variants": [
                        {"content_type": "video/mp4", "url": "https://example.com/gif.mp4", "bit_rate": 0},
                    ],
                }
            ]
        }
        result = TwitterClient.extract_media_urls(tweet, includes)
        assert len(result) == 1
        assert result[0]["type"] == "animated_gif"
        assert result[0]["media_key"] == "16_abc"

    def test_preserves_media_key_order(self):
        """Output order matches the order of media_keys in the tweet."""
        tweet: TweetData = {
            "id": "1",
            "text": "multi",
            "author_id": "u1",
            "attachments": {"media_keys": ["3_first", "3_second", "3_third"]},
        }
        includes: IncludesData = {
            "media": [
                {"media_key": "3_second", "type": "photo", "url": "https://second.jpg"},
                {"media_key": "3_third", "type": "photo", "url": "https://third.jpg"},
                {"media_key": "3_first", "type": "photo", "url": "https://first.jpg"},
            ]
        }
        result = TwitterClient.extract_media_urls(tweet, includes)
        assert [r["url"] for r in result] == [
            "https://first.jpg",
            "https://second.jpg",
            "https://third.jpg",
        ]


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class TestErrorTypes:
    """Test TwitterAPIError and RateLimitError."""

    def test_twitter_api_error_stores_status_code(self):
        """TwitterAPIError stores the status_code attribute."""
        err = TwitterAPIError("Something went wrong", 503)
        assert err.status_code == 503
        assert "Something went wrong" in str(err)

    def test_rate_limit_error_is_twitter_api_error(self):
        """RateLimitError is a subclass of TwitterAPIError."""
        err = RateLimitError()
        assert isinstance(err, TwitterAPIError)
        assert err.status_code == 429

    def test_rate_limit_error_stores_reset_at(self):
        """RateLimitError stores reset_at when provided."""
        err = RateLimitError(reset_at=1700000000)
        assert err.reset_at == 1700000000

    def test_rate_limit_error_reset_at_defaults_to_none(self):
        """RateLimitError reset_at is None when not provided."""
        err = RateLimitError()
        assert err.reset_at is None


# ---------------------------------------------------------------------------
# OAuth and Auth Tests (unchanged — testing auth.py)
# ---------------------------------------------------------------------------


class TestOAuth2PKCE:
    """Test OAuth 2.0 PKCE flow."""

    def test_oauth_init(self):
        """Test OAuth2PKCE initialization."""
        oauth = OAuth2PKCE("client_id_123")
        assert oauth.client_id == "client_id_123"

    def test_generate_code_verifier(self):
        """Test code verifier generation."""
        oauth = OAuth2PKCE("client_id")
        verifier = oauth._generate_code_verifier()

        assert isinstance(verifier, str)
        assert len(verifier) >= 43
        assert len(verifier) <= 128

    def test_generate_code_challenge(self):
        """Test code challenge generation from verifier."""
        oauth = OAuth2PKCE("client_id")
        verifier = oauth._generate_code_verifier()
        challenge = oauth._generate_code_challenge(verifier)

        assert isinstance(challenge, str)
        assert len(challenge) > 0

    def test_authorization_url_generation(self):
        """Test authorization URL generation."""
        oauth = OAuth2PKCE("client_id_123")
        auth_url = oauth.get_authorization_url()

        assert "https://twitter.com/i/oauth2/authorize" in auth_url
        assert "client_id=client_id_123" in auth_url
        assert "response_type=code" in auth_url
        assert "redirect_uri=http" in auth_url
        assert "code_challenge=" in auth_url
        assert oauth.code_verifier is not None
        assert oauth.state is not None


class TestAuthManager:
    """Test authentication manager."""

    @patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test_bearer_token"})
    @patch("bookmark_downloader.api.auth.TokenStore")
    def test_get_access_token_bearer(self, mock_token_store: Mock):
        """Test getting access token from bearer token."""
        manager = AuthManager({"paths": {"logs_directory": "/tmp"}})
        token = manager.get_access_token()

        assert token == "test_bearer_token"

    @patch.dict("os.environ", {}, clear=True)
    @patch("bookmark_downloader.api.auth.TokenStore")
    def test_get_access_token_missing_credentials(self, mock_token_store: Mock):
        """Test error when no credentials provided."""
        manager = AuthManager({"paths": {"logs_directory": "/tmp"}})

        with pytest.raises(ValueError, match="No authentication credentials found"):
            manager.get_access_token()


class TestMapQuotedTweetId:
    """Test _map_quoted_tweet_id helper method."""

    def test_returns_quoted_id_when_type_is_quoted(self):
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            result = client._map_quoted_tweet_id({
                "referenced_tweets": [{"type": "quoted", "id": "9876543210"}]
            })
        assert result == "9876543210"

    def test_returns_none_when_type_is_replied_to(self):
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            result = client._map_quoted_tweet_id({
                "referenced_tweets": [{"type": "replied_to", "id": "9876543210"}]
            })
        assert result is None

    def test_returns_none_when_no_referenced_tweets(self):
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            result = client._map_quoted_tweet_id({})
        assert result is None

    def test_returns_quoted_id_when_mixed_with_replied_to(self):
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            result = client._map_quoted_tweet_id({
                "referenced_tweets": [
                    {"type": "replied_to", "id": "1111111111"},
                    {"type": "quoted", "id": "9876543210"},
                ]
            })
        assert result == "9876543210"
