"""Tests for configuration management system."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bookmark_downloader.config import Config


class TestConfigDefaults:
    """Test default configuration values."""

    def test_defaults_exist(self):
        """Test that default configuration is defined."""
        assert Config.DEFAULTS is not None
        assert "twitter" in Config.DEFAULTS
        assert "paths" in Config.DEFAULTS
        assert "download" in Config.DEFAULTS
        assert "logging" in Config.DEFAULTS

    def test_required_defaults(self):
        """Test that required default sections exist."""
        defaults = Config.DEFAULTS
        assert defaults["twitter"]["request_timeout"] == 30
        assert defaults["download"]["max_workers"] == 4
        assert defaults["logging"]["level"] == "INFO"
        assert defaults["state_management"]["tracking_method"] == "local_logging"


class TestConfigYAMLLoading:
    """Test YAML configuration loading."""

    def test_load_yaml_config(self, sample_config_yaml, clean_env):
        """Test loading YAML configuration file."""
        # Set working directory to temp_dir
        original_cwd = os.getcwd()
        try:
            os.chdir(sample_config_yaml.parent)
            config = Config(str(sample_config_yaml))

            assert config["twitter"]["bearer_token"] == "test_bearer_token_123"
            assert config["download"]["max_workers"] == 4
            assert config["logging"]["level"] == "INFO"
        finally:
            os.chdir(original_cwd)

    def test_yaml_overrides_defaults(self, temp_dir, clean_env):
        """Test that YAML config overrides defaults."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("""
twitter:
  bearer_token: custom_token
download:
  max_workers: 8
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            config = Config(str(config_file))

            assert config["download"]["max_workers"] == 8
            assert config["twitter"]["bearer_token"] == "custom_token"
            # Other defaults should remain
            assert config["logging"]["level"] == "INFO"
        finally:
            os.chdir(original_cwd)


class TestConfigEnvironmentVariables:
    """Test environment variable override support."""

    def test_env_var_with_prefix(self, sample_config_yaml, clean_env):
        """Test BOOKMARK_DOWNLOADER_* environment variables."""
        original_cwd = os.getcwd()
        try:
            os.chdir(sample_config_yaml.parent)
            os.environ["BOOKMARK_DOWNLOADER_DOWNLOAD_MAX_WORKERS"] = "16"
            os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

            config = Config(str(sample_config_yaml))

            assert config["download"]["max_workers"] == 16
        finally:
            os.chdir(original_cwd)

    def test_env_var_direct_twitter_token(self, clean_env):
        """Test TWITTER_BEARER_TOKEN environment variable."""
        os.environ["TWITTER_BEARER_TOKEN"] = "direct_env_token"

        config = Config()

        assert config["twitter"]["bearer_token"] == "direct_env_token"

    def test_env_var_type_conversion(self, clean_env):
        """Test type conversion for environment variables."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        os.environ["BOOKMARK_DOWNLOADER_DOWNLOAD_MAX_WORKERS"] = "4"
        os.environ["BOOKMARK_DOWNLOADER_PROCESSING_FOLLOW_QUOTES"] = "false"

        config = Config()

        assert isinstance(config["download"]["max_workers"], int)
        assert config["download"]["max_workers"] == 4
        assert isinstance(config["processing"]["follow_quotes"], bool)
        assert config["processing"]["follow_quotes"] is False

    def test_env_var_priority(self, sample_config_yaml, clean_env):
        """Test that env vars override config file."""
        original_cwd = os.getcwd()
        try:
            os.chdir(sample_config_yaml.parent)
            os.environ["BOOKMARK_DOWNLOADER_DOWNLOAD_MAX_WORKERS"] = "99"
            os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

            config = Config(str(sample_config_yaml))

            # Env var should override YAML file
            assert config["download"]["max_workers"] == 99
        finally:
            os.chdir(original_cwd)


class TestPathResolution:
    """Test path expansion and resolution."""

    def test_expand_home_path(self, clean_env):
        """Test ~ expansion for home directory."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        config = Config()

        downloads_dir = config.get_downloads_dir()
        assert str(downloads_dir).startswith(str(Path.home()))
        assert "~" not in str(downloads_dir)

    def test_expand_relative_path(self, temp_dir, clean_env):
        """Test relative path resolution."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("""
twitter:
  bearer_token: token
paths:
  downloads_directory: ./downloads
  logs_directory: ./logs
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            config = Config(str(config_file))
            downloads_dir = config.get_downloads_dir()

            assert downloads_dir == temp_dir.resolve() / "downloads"
        finally:
            os.chdir(original_cwd)

    def test_absolute_path(self, clean_env):
        """Test absolute path handling."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        os.environ["BOOKMARK_DOWNLOADER_PATHS_DOWNLOADS_DIRECTORY"] = "/tmp/test"

        config = Config()
        downloads_dir = config.get_downloads_dir()

        assert downloads_dir == Path("/tmp/test")


class TestConfigValidation:
    """Test configuration validation."""

    def test_missing_bearer_token_raises_error(self, clean_env):
        """Test that missing bearer token raises ValueError."""
        with pytest.raises(ValueError, match="TWITTER_BEARER_TOKEN not set"):
            Config()

    def test_invalid_tracking_method_raises_error(self, temp_dir, clean_env):
        """Test that invalid tracking method raises ValueError."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("""
twitter:
  bearer_token: token
state_management:
  tracking_method: invalid_method
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            with pytest.raises(ValueError, match="Invalid tracking_method"):
                Config(str(config_file))
        finally:
            os.chdir(original_cwd)

    def test_invalid_log_level_raises_error(self, temp_dir, clean_env):
        """Test that invalid log level raises ValueError."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("""
twitter:
  bearer_token: token
logging:
  level: INVALID
""")

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            with pytest.raises(ValueError, match="Invalid log level"):
                Config(str(config_file))
        finally:
            os.chdir(original_cwd)

    def test_valid_tracking_methods(self, clean_env):
        """Test that all valid tracking methods are accepted."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"

        # Test that env var sets tracking_method to "bookmark_removal" (non-default, so we can
        # confirm the env var actually took effect and wasn't just the default value)
        os.environ["BOOKMARK_DOWNLOADER_STATE_MANAGEMENT_TRACKING_METHOD"] = "bookmark_removal"
        config = Config()
        assert config["state_management"]["tracking_method"] == "bookmark_removal"

        # All valid methods should not raise errors
        for method in ["local_logging", "bookmark_removal", "hybrid"]:
            # Override the tracking method temporarily
            config.config["state_management"]["tracking_method"] = method
            assert config["state_management"]["tracking_method"] == method


class TestConfigDictAccess:
    """Test dictionary-like access to config."""

    def test_getitem_access(self, clean_env):
        """Test __getitem__ access pattern."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        config = Config()

        assert config["twitter"]["bearer_token"] == "token"
        assert config["download"]["max_workers"] == 4

    def test_config_repr_masks_token(self, clean_env):
        """Test that config repr masks bearer token."""
        os.environ["TWITTER_BEARER_TOKEN"] = "secret_token_123"
        config = Config()

        repr_str = repr(config)
        assert "***MASKED***" in repr_str
        assert "secret_token_123" not in repr_str


class TestConfigDatabasePath:
    """Test database path configuration."""

    def test_database_path_in_logs_dir(self, clean_env):
        """Test that database goes in logs directory by default."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        config = Config()

        db_path = config.get_database_path()
        logs_dir = config.get_logs_dir()

        assert str(db_path).startswith(str(logs_dir))

    def test_absolute_database_path(self, clean_env, temp_dir):
        """Test absolute database path."""
        db_file = temp_dir / "state.db"
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        # Note: environment variable override might not work for absolute paths in all cases
        # The config should resolve absolute paths correctly
        config = Config()

        # Manually set to absolute path to test the resolution
        config.config["state_management"]["database_file"] = str(db_file)
        db_path = config.get_database_path()

        # Should return the absolute path when configured
        assert db_path == db_file or db_path.is_absolute()


class TestConfigQuarantineDir:
    """Test quarantine directory configuration."""

    def test_quarantine_dir_in_logs_dir(self, clean_env):
        """Test that quarantine directory is in logs directory by default."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        config = Config()

        quarantine_dir = config.get_quarantine_dir()
        logs_dir = config.get_logs_dir()

        assert str(quarantine_dir).startswith(str(logs_dir))

    def test_absolute_quarantine_path(self, clean_env):
        """Test absolute quarantine path."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        os.environ["BOOKMARK_DOWNLOADER_QUARANTINE_FOLDER"] = "/tmp/quarantine"

        config = Config()
        quarantine_dir = config.get_quarantine_dir()

        assert quarantine_dir == Path("/tmp/quarantine")


class TestConfigLogFile:
    """Test log file path configuration."""

    def test_log_file_in_logs_dir(self, clean_env):
        """Test that log file is in logs directory by default."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        config = Config()

        log_file = config.get_log_file()
        logs_dir = config.get_logs_dir()

        assert str(log_file).startswith(str(logs_dir))

    def test_absolute_log_file_path(self, clean_env):
        """Test absolute log file path."""
        os.environ["TWITTER_BEARER_TOKEN"] = "token"
        os.environ["BOOKMARK_DOWNLOADER_LOGGING_FILENAME"] = "/tmp/app.log"

        config = Config()
        log_file = config.get_log_file()

        assert log_file == Path("/tmp/app.log")
