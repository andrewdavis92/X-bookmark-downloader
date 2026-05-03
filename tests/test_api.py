"""Tests for X API client using official XDK."""

import json
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from bookmark_downloader.api.auth import AuthManager, OAuth2PKCE, TokenStore
from bookmark_downloader.api.twitter_client import RateLimitError, TwitterClient
from bookmark_downloader.api.types import TweetData


# Test fixtures


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
    """Sample bookmarks API response."""
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


@pytest.fixture
def twitter_client() -> TwitterClient:
    """Initialize test Twitter client with mocked XDK."""
    with patch("xdk.client.Client"):
        return TwitterClient(access_token="test_token_12345")


# Twitter Client Tests


class TestTwitterClientInitialization:
    """Test TwitterClient initialization."""

    @patch("xdk.client.Client")
    def test_client_init(self, mock_xdk_client: Mock):
        """Test client initializes with token."""
        client = TwitterClient(access_token="test_token_12345")
        assert client.access_token == "test_token_12345"
        mock_xdk_client.assert_called_once()

    @patch("xdk.client.Client")
    def test_client_xdk_initialization(self, mock_xdk_client: Mock):
        """Test XDK client is initialized with bearer token."""
        client = TwitterClient(access_token="test_token_12345")

        # Verify Client was called with bearer_token
        call_args = mock_xdk_client.call_args
        assert call_args[1]["bearer_token"] == "test_token_12345"


class TestBookmarkPagination:
    """Test bookmark fetching with pagination."""

    @patch("xdk.client.Client")
    def test_get_bookmarks_single_page(
        self,
        mock_client_class: Mock,
        sample_bookmark_response: dict,
    ):
        """Test fetching bookmarks when only one page."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_bookmark_response
        mock_response.headers = {
            "x-rate-limit-remaining": "179",
            "x-rate-limit-reset": str(int(time.time()) + 900),
        }

        # Setup mock client instance
        mock_client_instance = MagicMock()
        mock_client_instance.get_users_me_bookmarks.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        client = TwitterClient(access_token="test_token")
        bookmarks = list(client.get_bookmarks_iter(batch_size=100))

        assert len(bookmarks) == 1
        assert bookmarks[0]["id"] == "1234567890"
        assert bookmarks[0]["text"] == "This is a test tweet"

    @patch("xdk.client.Client")
    def test_get_bookmarks_pagination(
        self,
        mock_client_class: Mock,
        sample_tweet: TweetData,
    ):
        """Test automatic pagination through multiple pages."""
        tweet2: TweetData = {
            "id": "9876543210",
            "text": "Second tweet",
            "author_id": "user789",
            "created_at": "2024-04-04T12:00:00Z",
        }

        # First page response
        response1 = {
            "data": [sample_tweet],
            "meta": {
                "result_count": 1,
                "next_token": "abc123",
            },
        }

        # Second page response
        response2 = {
            "data": [tweet2],
            "meta": {"result_count": 1},
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = [response1, response2]
        mock_response.headers = {
            "x-rate-limit-remaining": "179",
            "x-rate-limit-reset": str(int(time.time()) + 900),
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get_users_me_bookmarks.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        client = TwitterClient(access_token="test_token")
        bookmarks = list(client.get_bookmarks_iter(batch_size=100))

        assert len(bookmarks) == 2
        assert bookmarks[0]["id"] == "1234567890"
        assert bookmarks[1]["id"] == "9876543210"

    @patch("xdk.client.Client")
    def test_get_bookmarks_empty(self, mock_client_class: Mock):
        """Test handling empty bookmark list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [], "meta": {"result_count": 0}}
        mock_response.headers = {
            "x-rate-limit-remaining": "179",
            "x-rate-limit-reset": str(int(time.time()) + 900),
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get_users_me_bookmarks.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        client = TwitterClient(access_token="test_token")
        bookmarks = list(client.get_bookmarks_iter())

        assert len(bookmarks) == 0


class TestRateLimitHandling:
    """Test automatic rate limit handling."""

    @patch("xdk.client.Client")
    @patch("time.sleep")
    def test_rate_limit_wait_and_retry(
        self,
        mock_sleep: Mock,
        mock_client_class: Mock,
        sample_bookmark_response: dict,
    ):
        """Test automatic wait and retry on rate limit."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {
            "x-rate-limit-remaining": "0",
            "x-rate-limit-reset": str(int(time.time()) + 10),
        }

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = sample_bookmark_response
        success_response.headers = {
            "x-rate-limit-remaining": "179",
            "x-rate-limit-reset": str(int(time.time()) + 900),
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get_users_me_bookmarks.side_effect = [
            rate_limit_response,
            success_response,
        ]
        mock_client_class.return_value = mock_client_instance

        client = TwitterClient(access_token="test_token")
        bookmarks = list(client.get_bookmarks_iter())

        assert len(bookmarks) == 1
        # Verify sleep was called
        assert mock_sleep.called

    @patch("xdk.client.Client")
    def test_rate_limit_max_retries_exceeded(
        self,
        mock_client_class: Mock,
    ):
        """Test exception when rate limit retries exhausted."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {
            "x-rate-limit-remaining": "0",
            "x-rate-limit-reset": str(int(time.time()) + 10),
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get_users_me_bookmarks.return_value = rate_limit_response
        mock_client_class.return_value = mock_client_instance

        client = TwitterClient(access_token="test_token")

        with pytest.raises(RateLimitError):
            list(client.get_bookmarks_iter())


class TestErrorHandling:
    """Test error handling for edge cases."""

    @patch("xdk.client.Client")
    def test_deleted_tweet_404_error(
        self,
        mock_client_class: Mock,
    ):
        """Test handling of deleted tweet (404)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {
            "x-rate-limit-remaining": "179",
            "x-rate-limit-reset": str(int(time.time()) + 900),
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get_tweets_id.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        client = TwitterClient(access_token="test_token")

        with pytest.raises(ValueError, match="deleted or inaccessible"):
            client.get_tweet_details("deleted_tweet_id")

    @patch("xdk.client.Client")
    def test_protected_tweet_403_error(
        self,
        mock_client_class: Mock,
    ):
        """Test handling of protected/private tweet (403)."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {
            "x-rate-limit-remaining": "179",
            "x-rate-limit-reset": str(int(time.time()) + 900),
        }

        mock_client_instance = MagicMock()
        mock_client_instance.get_tweets_id.return_value = mock_response
        mock_client_class.return_value = mock_client_instance

        client = TwitterClient(access_token="test_token")

        with pytest.raises(ValueError, match="access denied"):
            client.get_tweet_details("protected_tweet_id")

    def test_missing_required_field_id(self):
        """Test validation fails on missing id field."""
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            invalid_tweet = {"text": "No ID", "author_id": "user123"}

            with pytest.raises(ValueError, match="Missing required field: id"):
                client._validate_tweet(invalid_tweet)

    def test_missing_required_field_text(self):
        """Test validation fails on missing text field."""
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            invalid_tweet = {"id": "123", "author_id": "user123"}

            with pytest.raises(ValueError, match="Missing required field: text"):
                client._validate_tweet(invalid_tweet)

    def test_missing_required_field_author_id(self):
        """Test validation fails on missing author_id field."""
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            invalid_tweet = {"id": "123", "text": "No author"}

            with pytest.raises(ValueError, match="Missing required field: author_id"):
                client._validate_tweet(invalid_tweet)


class TestMediaExtraction:
    """Test media URL extraction from tweets."""

    def test_extract_media_urls_with_media(self, sample_tweet: TweetData):
        """Test extracting media URLs from tweet with attachments."""
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            media_urls = client.extract_media_urls(sample_tweet)

            assert isinstance(media_urls, list)

    def test_extract_media_urls_no_media(self, sample_tweet_no_media: TweetData):
        """Test extracting media from text-only tweet."""
        with patch("xdk.client.Client"):
            client = TwitterClient(access_token="test_token")
            media_urls = client.extract_media_urls(sample_tweet_no_media)

            assert len(media_urls) == 0


# OAuth and Auth Tests


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
