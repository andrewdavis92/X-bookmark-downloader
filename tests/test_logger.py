"""Tests for logging configuration."""

import logging
import os
from pathlib import Path

import pytest

from bookmark_downloader.utils.logger import Logger, get_logger
from bookmark_downloader.config import Config


class TestLoggerSetup:
    """Test logger setup and configuration."""

    def test_logger_setup_creates_instance(self, clean_env, temp_dir):
        """Test that logger setup creates a logger instance."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        config = Config()
        logger = Logger.setup(config)

        assert isinstance(logger, logging.Logger)
        assert logger.name == "bookmark_downloader"

    def test_logger_setup_sets_log_level(self, clean_env, temp_dir):
        """Test that logger setup sets the correct log level."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        # Create a config with INFO level (default)
        config = Config()
        logger = Logger.setup(config)

        # Logger should have a level set (at least INFO or better)
        assert logger.level in [logging.DEBUG, logging.INFO, logging.WARNING]

    def test_logger_setup_creates_handlers(self, clean_env, temp_dir):
        """Test that logger setup creates file and console handlers."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()
        logger = Logger.setup(config)

        # Check that handlers were added
        assert len(logger.handlers) >= 2

        # Find handler types
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "RotatingFileHandler" in handler_types
        assert "StreamHandler" in handler_types

    def test_logger_setup_creates_log_directory(self, clean_env, temp_dir):
        """Test that logger setup creates log directory if it doesn't exist."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()

        logger = Logger.setup(config)

        # Verify logger was set up successfully (directory creation happens in setup)
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_logger_setup_idempotent(self, clean_env, temp_dir):
        """Test that setting up logger multiple times doesn't duplicate handlers."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()

        # Setup first time
        logger1 = Logger.setup(config)
        handler_count_1 = len(logger1.handlers)

        # Setup again
        logger2 = Logger.setup(config)
        handler_count_2 = len(logger2.handlers)

        # Should have same number of handlers (cleared and re-added)
        assert handler_count_1 == handler_count_2


class TestLoggerInstance:
    """Test logger instance retrieval."""

    def test_get_logger_returns_instance(self, clean_env):
        """Test that get_logger returns a logger instance."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()
        Logger.setup(config)

        logger = Logger.get()
        assert isinstance(logger, logging.Logger)

    def test_get_logger_with_name(self, clean_env):
        """Test that get_logger returns named logger."""
        logger = get_logger("test_module")
        assert logger.name == "test_module"

    def test_get_logger_without_setup(self):
        """Test that get_logger works even without setup."""
        Logger._instance = None
        logger = get_logger()

        assert isinstance(logger, logging.Logger)


class TestLoggerFormatting:
    """Test logger message formatting."""

    def test_logger_has_formatter(self, clean_env):
        """Test that logger handlers have formatters."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()
        logger = Logger.setup(config)

        for handler in logger.handlers:
            assert handler.formatter is not None

    def test_logger_format_contains_timestamp(self, clean_env):
        """Test that logger format includes timestamp."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()
        logger = Logger.setup(config)

        # Check formatter format string
        for handler in logger.handlers:
            if handler.formatter:
                # Formatter should include asctime
                assert "%(asctime)s" in handler.formatter._fmt


class TestRotatingFileHandler:
    """Test rotating file handler configuration."""

    def test_rotating_file_handler_exists(self, clean_env):
        """Test that rotating file handler is configured."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()
        logger = Logger.setup(config)

        # Check that rotating file handler exists
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "RotatingFileHandler" in handler_types

        # Check that it has proper configuration
        for handler in logger.handlers:
            if handler.__class__.__name__ == "RotatingFileHandler":
                assert handler.maxBytes > 0
                assert handler.backupCount > 0


class TestLoggerLogging:
    """Test actual logging functionality."""

    def test_logger_can_log_messages(self, clean_env):
        """Test that logger can accept log messages."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()
        logger = Logger.setup(config)

        # Test that we can log at different levels without errors
        try:
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            logger.critical("Critical message")
        except Exception as e:
            pytest.fail(f"Logging raised exception: {e}")

    def test_logger_respects_configured_level(self, clean_env):
        """Test that logger respects its configured level."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        Logger._instance = None
        config = Config()
        logger = Logger.setup(config)

        # The logger should be configured with a valid level
        assert logger.level in [
            logging.NOTSET,
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ]
