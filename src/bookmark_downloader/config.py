"""Configuration management for X Bookmark Downloader.

Loads configuration from multiple sources in order of precedence:
1. Environment variables (highest priority)
2. config.yaml or config.json file
3. .env file
4. Hardcoded defaults (lowest priority)
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


class Config:
    """Configuration management with multiple source support."""

    # Default values
    DEFAULTS = {
        "twitter": {
            "bearer_token": None,
            "request_timeout": 30,
        },
        "paths": {
            "downloads_directory": "~/Documents/X-Bookmarks",
            "logs_directory": "~/Library/Logs/bookmark-downloader",
        },
        "download": {
            "image_quality": "high",
            "video_quality": "best",
            "max_workers": 4,
            "timeout_seconds": 600,
            "retry_attempts": 3,
        },
        "processing": {
            "follow_quotes": True,
            "max_quote_depth": 1,
            "batch_size": 100,
        },
        "state_management": {
            "database_file": "state.db",
            "tracking_method": "local_logging",  # local_logging, bookmark_removal, or hybrid
            "retention_days": 90,
        },
        "logging": {
            "level": "INFO",
            "filename": "bookmark_downloader.log",
            "max_bytes": 10485760,  # 10MB
            "backup_count": 5,
        },
        "quarantine": {
            "folder": "quarantine",
        },
    }

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration.

        Args:
            config_file: Path to config.yaml or config.json. If None, searches for config files.
        """
        self.config: Dict[str, Any] = self._load_config(config_file)
        self._validate_config()

    def _load_config(self, config_file: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from all sources.

        Priority order:
        1. Hardcoded defaults
        2. Config file (YAML or JSON)
        3. .env file
        4. Environment variables
        """
        # Start with defaults
        config = self._deep_copy(self.DEFAULTS)

        # Load .env file if it exists (searches up directory tree)
        load_dotenv()

        # Load config file
        if config_file:
            config = self._load_config_file(config_file, config)
        else:
            # Try to find config.yaml or config.json
            for filename in ["config.yaml", "config.yml", "config.json"]:
                if Path(filename).exists():
                    config = self._load_config_file(filename, config)
                    break

        # Load environment variables
        config = self._load_env_vars(config)

        return config

    @staticmethod
    def _load_config_file(
        filepath: str, base_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Load configuration from YAML or JSON file."""
        path = Path(filepath)

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")

        try:
            if filepath.endswith((".yaml", ".yml")):
                with open(path, "r") as f:
                    file_config = yaml.safe_load(f) or {}
            elif filepath.endswith(".json"):
                import json

                with open(path, "r") as f:
                    file_config = json.load(f)
            else:
                raise ValueError(f"Unsupported config file format: {filepath}")

            # Merge file config with base config (file takes precedence)
            return Config._deep_merge(base_config, file_config)
        except Exception as e:
            print(f"Error loading config file {filepath}: {e}", file=sys.stderr)
            raise

    @staticmethod
    def _load_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
        """Load configuration from environment variables.

        Supports two formats:
        1. BOOKMARK_DOWNLOADER_SECTION_KEY (e.g., BOOKMARK_DOWNLOADER_TWITTER_BEARER_TOKEN)
        2. Direct variables from .env (e.g., TWITTER_BEARER_TOKEN)
        """
        env_config = {}

        # First, handle BOOKMARK_DOWNLOADER_ prefixed variables
        for key, value in os.environ.items():
            if key.startswith("BOOKMARK_DOWNLOADER_"):
                # Remove prefix and convert to lowercase
                parts = key.replace("BOOKMARK_DOWNLOADER_", "").lower().split("_")

                # Build nested dict structure
                if len(parts) >= 2:
                    section = parts[0]
                    key_name = "_".join(parts[1:])

                    if section not in env_config:
                        env_config[section] = {}

                    # Try to convert value to appropriate type
                    env_config[section][key_name] = Config._parse_env_value(value)

        # Also check for direct environment variables from .env
        if "TWITTER_BEARER_TOKEN" in os.environ:
            if "twitter" not in env_config:
                env_config["twitter"] = {}
            env_config["twitter"]["bearer_token"] = os.environ["TWITTER_BEARER_TOKEN"]

        return Config._deep_merge(config, env_config)

    @staticmethod
    def _parse_env_value(value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Handle boolean values
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Handle integer values
        if value.isdigit():
            return int(value)

        # Handle float values
        try:
            return float(value)
        except ValueError:
            pass

        # Return as string
        return value

    @staticmethod
    def _deep_copy(obj: Dict[str, Any]) -> Dict[str, Any]:
        """Create a deep copy of nested dictionary."""
        if isinstance(obj, dict):
            return {k: Config._deep_copy(v) for k, v in obj.items()}
        return obj

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge override into base dictionary."""
        result = Config._deep_copy(base)

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _validate_config(self) -> None:
        """Validate configuration values."""
        # Validate required fields
        if not self.config.get("twitter", {}).get("bearer_token"):
            raise ValueError("TWITTER_BEARER_TOKEN not set. Set via .env or config file.")

        # Validate tracking method
        tracking_method = self.config.get("state_management", {}).get("tracking_method")
        valid_methods = {"local_logging", "bookmark_removal", "hybrid"}
        if tracking_method not in valid_methods:
            raise ValueError(
                f"Invalid tracking_method: {tracking_method}. "
                f"Must be one of: {valid_methods}"
            )

        # Validate log level
        log_level = self.config.get("logging", {}).get("level", "").upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level not in valid_levels:
            raise ValueError(
                f"Invalid log level: {log_level}. Must be one of: {valid_levels}"
            )

    def expand_path(self, path_str: str) -> Path:
        """Expand path with support for ~, ./, and absolute paths."""
        path = Path(path_str)

        # Expand ~ to home directory
        if path_str.startswith("~"):
            path = path.expanduser()
        # Expand ./ relative paths
        elif path_str.startswith("./"):
            path = Path.cwd() / path_str[2:]

        return path

    def get_downloads_dir(self) -> Path:
        """Get the downloads directory, expanding path variables."""
        path_str = self.config["paths"]["downloads_directory"]
        return self.expand_path(path_str)

    def get_logs_dir(self) -> Path:
        """Get the logs directory, expanding path variables."""
        path_str = self.config["paths"]["logs_directory"]
        return self.expand_path(path_str)

    def get_database_path(self) -> Path:
        """Get the database file path."""
        db_file = self.config["state_management"]["database_file"]
        logs_dir = self.get_logs_dir()

        # If absolute path, use as-is
        if Path(db_file).is_absolute():
            return Path(db_file)

        # Otherwise, place in logs directory
        return logs_dir / db_file

    def get_quarantine_dir(self) -> Path:
        """Get the quarantine directory."""
        quarantine_folder = self.config["quarantine"]["folder"]
        logs_dir = self.get_logs_dir()

        # If absolute path, use as-is
        if Path(quarantine_folder).is_absolute():
            return Path(quarantine_folder)

        # Otherwise, place in logs directory
        return logs_dir / quarantine_folder

    def get_log_file(self) -> Path:
        """Get the log file path."""
        log_filename = self.config["logging"]["filename"]
        logs_dir = self.get_logs_dir()

        # If absolute path, use as-is
        if Path(log_filename).is_absolute():
            return Path(log_filename)

        # Otherwise, place in logs directory
        return logs_dir / log_filename

    def __getitem__(self, key: str) -> Any:
        """Allow dict-like access to config."""
        return self.config[key]

    def __repr__(self) -> str:
        """String representation of config (without sensitive data)."""
        safe_config = self._deep_copy(self.config)
        # Mask bearer token
        if safe_config.get("twitter", {}).get("bearer_token"):
            safe_config["twitter"]["bearer_token"] = "***MASKED***"
        return f"Config({safe_config})"


# Global config instance
_config: Optional[Config] = None


def get_config(config_file: Optional[str] = None) -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config(config_file)
    return _config


def reload_config(config_file: Optional[str] = None) -> Config:
    """Reload configuration from file."""
    global _config
    _config = Config(config_file)
    return _config
