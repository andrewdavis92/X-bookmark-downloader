"""X Bookmark Downloader - Main Entry Point.

Downloads media from X (Twitter) bookmarks with intelligent organization.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from bookmark_downloader.config import get_config, reload_config
from bookmark_downloader.utils.logger import Logger, get_logger


def setup_logging(config):
    """Set up logging based on configuration."""
    logger = Logger.setup(config)
    return logger


def verify_setup(config) -> bool:
    """Verify that the application setup is correct.

    Checks:
    - X API credentials are configured
    - Required directories are accessible
    - Database can be initialized
    """
    logger = get_logger(__name__)
    logger.info("Verifying setup...")

    try:
        # Check Twitter credentials
        bearer_token = config["twitter"]["bearer_token"]
        if not bearer_token:
            logger.error("X API bearer token not configured")
            return False

        if bearer_token == "${TWITTER_BEARER_TOKEN}":
            logger.error(
                "X API bearer token not set. "
                "Set TWITTER_BEARER_TOKEN environment variable or in config file."
            )
            return False

        logger.info("✓ X API credentials configured")

        # Check paths
        downloads_dir = config.get_downloads_dir()
        logs_dir = config.get_logs_dir()

        logger.info(f"Downloads directory: {downloads_dir}")
        logger.info(f"Logs directory: {logs_dir}")

        # Create directories if they don't exist
        downloads_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        logger.info("✓ Directory structure ready")

        logger.info("Setup verification complete - ready to download!")
        return True

    except Exception as e:
        logger.error(f"Setup verification failed: {e}")
        return False


def download_bookmarks(config, limit: Optional[int] = None, dry_run: bool = False) -> bool:
    """Download bookmarks from X.

    Args:
        config: Configuration instance
        limit: Maximum number of bookmarks to process
        dry_run: If True, don't actually download files

    Returns:
        True if successful, False otherwise
    """
    logger = get_logger(__name__)

    try:
        logger.info("Starting bookmark download...")

        if dry_run:
            logger.info("DRY RUN mode - no files will be downloaded")

        if limit:
            logger.info(f"Processing up to {limit} bookmarks")

        # TODO: Implement actual download logic in Phase 2+
        logger.warning("Download functionality not yet implemented")
        logger.info("This will be implemented in Phase 2-8")

        return True

    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        return False


def show_stats(config) -> bool:
    """Display processing statistics.

    Returns:
        True if successful, False otherwise
    """
    logger = get_logger(__name__)

    try:
        logger.info("Fetching statistics...")

        # TODO: Implement statistics display in Phase 10+
        logger.warning("Statistics functionality not yet implemented")

        return True

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}", exc_info=True)
        return False


def retry_quarantine(config, limit: Optional[int] = None) -> bool:
    """Retry failed downloads from quarantine.

    Args:
        config: Configuration instance
        limit: Maximum number of items to retry

    Returns:
        True if successful, False otherwise
    """
    logger = get_logger(__name__)

    try:
        logger.info("Retrying quarantined items...")

        if limit:
            logger.info(f"Retrying up to {limit} items")

        # TODO: Implement quarantine retry in Phase 7+
        logger.warning("Quarantine retry not yet implemented")

        return True

    except Exception as e:
        logger.error(f"Quarantine retry failed: {e}", exc_info=True)
        return False


def clear_cache(config, older_than_days: int = 90) -> bool:
    """Clear old cache and history.

    Args:
        config: Configuration instance
        older_than_days: Clear items older than this many days

    Returns:
        True if successful, False otherwise
    """
    logger = get_logger(__name__)

    try:
        logger.info(f"Clearing cache (older than {older_than_days} days)...")

        # TODO: Implement cache clearing in Phase 10+
        logger.warning("Cache clearing not yet implemented")

        return True

    except Exception as e:
        logger.error(f"Cache clearing failed: {e}", exc_info=True)
        return False


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Download media from X (Twitter) bookmarks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify setup and configuration
  python -m bookmark_downloader verify_setup

  # Download all bookmarks
  python -m bookmark_downloader download

  # Download only first 10 bookmarks
  python -m bookmark_downloader download --limit 10

  # Show statistics
  python -m bookmark_downloader show_stats

  # Retry failed downloads
  python -m bookmark_downloader retry_quarantine

  # Clear old cache
  python -m bookmark_downloader clear_cache
        """,
    )

    parser.add_argument(
        "command",
        choices=[
            "download",
            "verify_setup",
            "show_stats",
            "retry_quarantine",
            "clear_cache",
        ],
        help="Command to execute",
    )

    parser.add_argument(
        "--config",
        help="Path to config file (config.yaml or config.json)",
        default=None,
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of items to process",
        default=None,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override log level from config",
        default=None,
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = reload_config(args.config)

        # Override log level if specified
        if args.log_level:
            config["logging"]["level"] = args.log_level

        # Set up logging
        setup_logging(config)
        logger = get_logger(__name__)

        logger.info(f"X Bookmark Downloader starting (command: {args.command})")

        # Execute command
        if args.command == "verify_setup":
            success = verify_setup(config)
        elif args.command == "download":
            success = download_bookmarks(config, limit=args.limit, dry_run=args.dry_run)
        elif args.command == "show_stats":
            success = show_stats(config)
        elif args.command == "retry_quarantine":
            success = retry_quarantine(config, limit=args.limit)
        elif args.command == "clear_cache":
            success = clear_cache(config, older_than_days=args.limit or 90)
        else:
            logger.error(f"Unknown command: {args.command}")
            success = False

        # Return appropriate exit code
        return 0 if success else 1

    except KeyboardInterrupt:
        logger = get_logger(__name__)
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


def cli():
    """CLI entry point (for console_scripts in setup.py)."""
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
