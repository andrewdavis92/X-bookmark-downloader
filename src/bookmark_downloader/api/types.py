"""Type definitions for X API responses and internal data structures."""

from typing import Any, Dict, List, NotRequired, Optional, TypedDict


class MediaData(TypedDict):
    """Media object from X API."""

    media_key: str
    type: str  # "photo", "video", "animated_gif"
    url: NotRequired[str]
    alt_text: NotRequired[str]


class UserData(TypedDict):
    """User object from X API."""

    id: str
    username: str
    created_at: NotRequired[str]


class TweetData(TypedDict):
    """Tweet object from X API."""

    id: str
    text: str
    author_id: NotRequired[str]
    created_at: NotRequired[str]
    attachments: NotRequired[Dict[str, List[str]]]  # e.g. {"media_keys": ["7_1234"]}
    quoted_tweet_id: NotRequired[str]


class BookmarkResponse(TypedDict):
    """Response containing bookmarks from X API."""

    data: List[TweetData]
    includes: NotRequired[Dict[str, Any]]
    meta: NotRequired[Dict[str, Any]]


class MediaUrl(TypedDict):
    """Extracted media URL for download."""

    url: str
    type: str  # "photo", "video", "animated_gif"
    media_key: NotRequired[str]
    alt_text: NotRequired[str]


class RateLimitStatus(TypedDict):
    """Rate limit information."""

    remaining: int
    limit: int
    reset_timestamp: int


class OAuthTokenResponse(TypedDict):
    """OAuth token response from X API."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: NotRequired[str]
    scope: str


class EncryptedToken(TypedDict):
    """Encrypted token stored in database."""

    encrypted_data: str
    nonce: str  # IV for encryption
