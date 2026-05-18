"""Logging configuration for X Bookmark Downloader."""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

from bookmark_downloader.config import Config


class Logger:
    """Logging setup and management."""

    _instance: Optional[logging.Logger] = None

    @staticmethod
    def setup(config: Config) -> logging.Logger:
        """Set up logging with file rotation and console output.

        Args:
            config: Configuration instance

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger("bookmark_downloader")

        # Clear existing handlers (idempotent — prevents duplicates on repeated setup)
        logger.handlers.clear()

        # Set log level
        log_level = config["logging"]["level"].upper()
        logger.setLevel(getattr(logging, log_level))

        # Create logs directory if it doesn't exist
        config.get_logs_dir().mkdir(parents=True, exist_ok=True)
        log_file = config.get_log_file()

        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=config["logging"]["max_bytes"],
            backupCount=config["logging"]["backup_count"],
        )
        file_handler.setLevel(getattr(logging, log_level))

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level))

        # Formatter
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        Logger._instance = logger
        return logger

    @staticmethod
    def get() -> logging.Logger:
        """Get the configured logger instance."""
        if Logger._instance is None:
            # Return root logger if not configured
            return logging.getLogger("bookmark_downloader")
        return Logger._instance


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Module name (usually __name__)

    Returns:
        Logger instance
    """
    if name:
        return logging.getLogger(name)
    return Logger.get()
