"""X API authentication handling with OAuth 2.0 PKCE and bearer token support."""

import base64
import hashlib
import os
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from bookmark_downloader.config import get_config
from bookmark_downloader.utils.logger import get_logger

from .types import EncryptedToken, OAuthTokenResponse

logger = get_logger(__name__)


class TokenEncryption:
    """Handle encryption and decryption of tokens for secure storage."""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize token encryption.

        Args:
            encryption_key: Encryption key (base64 encoded). If None, generates new key.
        """
        try:
            from cryptography.fernet import Fernet

            self.cipher = Fernet(encryption_key.encode()) if encryption_key else Fernet(
                Fernet.generate_key()
            )
        except ImportError:
            logger.warning(
                "cryptography library not available, tokens will not be encrypted"
            )
            self.cipher = None

    @property
    def key(self) -> str:
        """Get the encryption key in base64 format."""
        if self.cipher:
            return self.cipher._signing_key + self.cipher._encryption_key
        return ""

    def encrypt(self, token: str) -> EncryptedToken:
        """
        Encrypt a token.

        Args:
            token: The token to encrypt.

        Returns:
            EncryptedToken with encrypted_data and nonce.
        """
        if not self.cipher:
            # Fallback: store unencrypted (not recommended for production)
            return {
                "encrypted_data": base64.b64encode(token.encode()).decode(),
                "nonce": base64.b64encode(os.urandom(16)).decode(),
            }

        encrypted = self.cipher.encrypt(token.encode())
        return {
            "encrypted_data": encrypted.decode(),
            "nonce": base64.b64encode(os.urandom(16)).decode(),
        }

    def decrypt(self, encrypted_token: EncryptedToken) -> str:
        """
        Decrypt a token.

        Args:
            encrypted_token: The encrypted token data.

        Returns:
            The decrypted token string.

        Raises:
            ValueError: If decryption fails.
        """
        if not self.cipher:
            # Fallback: decode unencrypted
            try:
                return base64.b64decode(encrypted_token["encrypted_data"]).decode()
            except Exception as e:
                raise ValueError("Failed to decode token") from e

        try:
            from cryptography.fernet import InvalidToken

            decrypted = self.cipher.decrypt(encrypted_token["encrypted_data"].encode())
            return decrypted.decode()
        except InvalidToken as e:
            raise ValueError("Failed to decrypt token - it may be corrupted") from e


class OAuth2PKCEHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth 2.0 callback."""

    auth_code: Optional[str] = None
    auth_state: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self) -> None:
        """Handle OAuth callback."""
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        if "code" in query_params:
            OAuth2PKCEHandler.auth_code = query_params["code"][0]
            OAuth2PKCEHandler.auth_state = query_params.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization successful!</h1>"
                b"<p>You can close this window and return to the CLI.</p></body></html>"
            )
            logger.info("OAuth authorization received")
        else:
            OAuth2PKCEHandler.error = query_params.get("error", ["Unknown error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authorization failed!</h1>"
                b"<p>Check the CLI for details.</p></body></html>"
            )
            logger.error(f"OAuth error: {OAuth2PKCEHandler.error}")

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress HTTP server logging."""
        pass


class OAuth2PKCE:
    """OAuth 2.0 with PKCE (Proof Key for Code Exchange) flow handler."""

    REDIRECT_URI = "http://localhost:8000/callback"
    AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
    TOKEN_URL = "https://api.x.com/2/oauth2/token"
    SCOPES = ["tweet.read", "users.read", "bookmark.read", "offline.access"]

    def __init__(self, client_id: str):
        """
        Initialize OAuth 2.0 PKCE handler.

        Args:
            client_id: X API application Client ID.
        """
        self.client_id = client_id
        self.code_verifier: Optional[str] = None
        self.state: Optional[str] = None

    def _generate_code_verifier(self) -> str:
        """Generate PKCE code verifier (43-128 unreserved characters)."""
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")

    def _generate_code_challenge(self, verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def get_authorization_url(self) -> str:
        """
        Generate authorization URL for user to visit.

        Returns:
            Authorization URL string.
        """
        self.code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(self.code_verifier)
        self.state = secrets.token_urlsafe(32)

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.REDIRECT_URI,
            "scope": " ".join(self.SCOPES),
            "state": self.state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.AUTHORIZE_URL}?{urlencode(params)}"

    def exchange_code_for_token(self, auth_code: str) -> OAuthTokenResponse:
        """
        Exchange authorization code for access token.

        Args:
            auth_code: Authorization code from OAuth callback.

        Returns:
            OAuthTokenResponse with access_token and refresh_token.

        Raises:
            ValueError: If token exchange fails.
        """
        if not self.code_verifier:
            raise ValueError("Code verifier not set - call get_authorization_url first")

        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": self.client_id,
            "redirect_uri": self.REDIRECT_URI,
            "code_verifier": self.code_verifier,
        }

        with httpx.Client() as client:
            response = client.post(self.TOKEN_URL, data=payload, timeout=30.0)
            response.raise_for_status()
            token_data = response.json()

            return {
                "access_token": token_data["access_token"],
                "token_type": token_data.get("token_type", "Bearer"),
                "expires_in": token_data.get("expires_in", 7200),
                "refresh_token": token_data.get("refresh_token"),
                "scope": token_data.get("scope", ""),
            }

    def refresh_access_token(self, refresh_token: str) -> OAuthTokenResponse:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token.

        Returns:
            OAuthTokenResponse with new access_token.

        Raises:
            ValueError: If token refresh fails.
        """
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
        }

        with httpx.Client() as client:
            response = client.post(self.TOKEN_URL, data=payload, timeout=30.0)
            response.raise_for_status()
            token_data = response.json()

            return {
                "access_token": token_data["access_token"],
                "token_type": token_data.get("token_type", "Bearer"),
                "expires_in": token_data.get("expires_in", 7200),
                "refresh_token": token_data.get("refresh_token", refresh_token),
                "scope": token_data.get("scope", ""),
            }


class TokenStore:
    """Manage token storage in SQLite database with encryption."""

    def __init__(self, db_path: Path, encryption_key: Optional[str] = None):
        """
        Initialize token store.

        Args:
            db_path: Path to SQLite database file.
            encryption_key: Encryption key for tokens. If None, uses environment variable.
        """
        self.db_path = db_path
        self.encryption = TokenEncryption(encryption_key)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize tokens table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oauth_tokens (
                    id INTEGER PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    expires_at INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def store_token(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: int = 7200,
    ) -> None:
        """
        Store OAuth token in database (encrypted).

        Args:
            access_token: The access token.
            refresh_token: Optional refresh token.
            expires_in: Token expiration time in seconds.
        """
        import time

        expires_at = int(time.time()) + expires_in

        # Encrypt the token before storing
        encrypted_access = self.encryption.encrypt(access_token)
        encrypted_refresh = None
        if refresh_token:
            encrypted_refresh = self.encryption.encrypt(refresh_token)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO oauth_tokens
                (access_token, refresh_token, expires_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    encrypted_access["encrypted_data"],
                    encrypted_refresh["encrypted_data"] if encrypted_refresh else None,
                    expires_at,
                ),
            )
            conn.commit()

        logger.info("OAuth token stored in database (encrypted)")

    def get_token(self) -> Optional[str]:
        """
        Retrieve and decrypt stored access token.

        Returns:
            Decrypted access token string, or None if not stored.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT access_token FROM oauth_tokens LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None

            try:
                encrypted_token: EncryptedToken = {
                    "encrypted_data": row[0],
                    "nonce": "",  # Not stored, but required for type
                }
                return self.encryption.decrypt(encrypted_token)
            except ValueError as e:
                logger.error(f"Failed to decrypt token: {e}")
                return None

    def get_refresh_token(self) -> Optional[str]:
        """
        Retrieve and decrypt stored refresh token.

        Returns:
            Decrypted refresh token string, or None if not stored.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT refresh_token FROM oauth_tokens LIMIT 1")
            row = cursor.fetchone()
            if not row or not row[0]:
                return None

            try:
                encrypted_token: EncryptedToken = {
                    "encrypted_data": row[0],
                    "nonce": "",
                }
                return self.encryption.decrypt(encrypted_token)
            except ValueError as e:
                logger.error(f"Failed to decrypt refresh token: {e}")
                return None


class AuthManager:
    """Main authentication manager for X API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize authentication manager.

        Args:
            config: Configuration dictionary. If None, loads from config file.
        """
        self.config = config or load_config()
        self.logs_dir = Path(self.config["paths"]["logs_directory"])
        self.db_path = self.logs_dir / "state.db"
        self.token_store = TokenStore(self.db_path)

    def get_access_token(self, skip_storage: bool = False) -> str:
        """
        Get valid access token using bearer token or OAuth.

        Args:
            skip_storage: If True, don't store tokens in database.

        Returns:
            Valid access token string.

        Raises:
            ValueError: If authentication fails.
        """
        # Try bearer token first (highest priority)
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        if bearer_token:
            logger.info("Using bearer token authentication")
            return bearer_token

        # Try OAuth flow
        client_id = os.getenv("TWITTER_CLIENT_ID")
        if not client_id:
            raise ValueError(
                "No authentication credentials found. Please set either:\n"
                "  - TWITTER_BEARER_TOKEN (for simple bearer token auth)\n"
                "  - TWITTER_CLIENT_ID (for OAuth 2.0 flow)\n"
                "\nSee config.example.yaml for more information."
            )

        logger.info("Starting OAuth 2.0 PKCE flow")
        return self._oauth_flow(client_id, skip_storage)

    def _oauth_flow(self, client_id: str, skip_storage: bool = False) -> str:
        """
        Execute OAuth 2.0 PKCE flow.

        Args:
            client_id: X API Client ID.
            skip_storage: If True, don't store tokens in database.

        Returns:
            Access token string.

        Raises:
            ValueError: If OAuth flow fails.
        """
        oauth = OAuth2PKCE(client_id)
        auth_url = oauth.get_authorization_url()

        # Start local callback server
        server = HTTPServer(("localhost", 8000), OAuth2PKCEHandler)
        server_thread = threading.Thread(target=server.handle_request, daemon=True)
        server_thread.start()

        logger.info(f"Opening browser for authorization: {auth_url}")
        logger.info("Waiting for authorization callback (timeout: 60s)...")

        # Print URL for user
        print(f"\n🔐 Authorization required!")
        print(f"Open this URL in your browser:\n{auth_url}\n")

        # Wait for callback with timeout
        server_thread.join(timeout=60)

        if OAuth2PKCEHandler.error:
            raise ValueError(f"OAuth authorization failed: {OAuth2PKCEHandler.error}")

        if not OAuth2PKCEHandler.auth_code:
            raise ValueError("Authorization timeout - no callback received")

        # Exchange code for token
        try:
            token_response = oauth.exchange_code_for_token(OAuth2PKCEHandler.auth_code)
        except Exception as e:
            raise ValueError(f"Failed to exchange authorization code: {e}") from e

        # Store token if not skipped
        if not skip_storage:
            self.token_store.store_token(
                token_response["access_token"],
                token_response.get("refresh_token"),
                token_response["expires_in"],
            )

        logger.info("OAuth authentication successful")
        return token_response["access_token"]
