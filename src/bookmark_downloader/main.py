"""X Bookmark Downloader - Main Entry Point.

Downloads media from X (Twitter) bookmarks with intelligent organization.
"""

import argparse
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from bookmark_downloader.api.twitter_client import (
    IncludesData,
    RateLimitError,
    TweetData,
    TwitterClient,
)
from bookmark_downloader.config import Config, get_config, reload_config
from bookmark_downloader.download.media_handler import MediaItem, coordinate_downloads
from bookmark_downloader.storage.database import StateManager
from bookmark_downloader.storage.local_storage import LocalStorage
from bookmark_downloader.storage.quarantine import (
    ErrorCategory,
    QuarantineManager,
    classify_error,
)
from bookmark_downloader.utils.logger import Logger, get_logger


_shutdown_requested: bool = False


def _handle_shutdown_signal(signum: int, frame: Any) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    get_logger(__name__).info(
        "Shutdown signal %d received, stopping after current tweet...", signum
    )


def _media_ext(media_url: Dict[str, str]) -> str:
    """Return the file extension (without dot) for a media URL dict."""
    parsed = urlparse(media_url["url"])
    suffix = Path(parsed.path).suffix
    return suffix.lstrip(".") if suffix else "bin"


def _find_user(user_id: str, includes: Dict) -> Optional[Dict]:
    """Return the user dict matching user_id from includes, or None."""
    for user in (includes.get("users") or []):
        if user.get("id") == user_id:
            return user
    return None


def _process_tweet(
    tweet_data: Dict,
    includes: Dict,
    api_client: TwitterClient,
    storage: LocalStorage,
    state: StateManager,
    config: Config,
    dry_run: bool = False,
) -> int:
    """Process one bookmark tweet. Returns number of media files downloaded."""
    logger = get_logger(__name__)
    tweet_id = tweet_data["id"]
    author_id = tweet_data.get("author_id", "")

    author_user = _find_user(author_id, includes)
    author_username = author_user["username"] if author_user else author_id

    # Find quoted tweet ID from referenced_tweets
    quoted_tweet_id: Optional[str] = None
    for ref in (tweet_data.get("referenced_tweets") or []):
        if ref.get("type") == "quoted":
            quoted_tweet_id = ref.get("id")
            break

    quoted_tweet_data: Optional[Dict] = None
    quoted_author_username: Optional[str] = None
    if quoted_tweet_id:
        expanded = {t["id"]: t for t in (includes.get("tweets") or [])}
        quoted_tweet_data = expanded.get(quoted_tweet_id)
        if quoted_tweet_data is None:
            quoted_tweet_data = api_client.get_tweet_details(quoted_tweet_id)
        if quoted_tweet_data:
            quid = quoted_tweet_data.get("author_id", "")
            quoted_user = _find_user(quid, includes)
            quoted_author_username = quoted_user["username"] if quoted_user else (quid or None)

    # Extract media URLs and build download items
    media_urls = api_client.extract_media_urls(tweet_data, includes)
    media_filenames: List[str] = []
    media_items: List[MediaItem] = []
    for idx, media_url in enumerate(media_urls, start=1):
        ext = _media_ext(media_url)
        dest = storage.get_media_path(author_username, tweet_id, idx, ext)
        media_filenames.append(dest.name)
        media_items.append(MediaItem(
            url=media_url["url"],
            media_type=media_url["type"],
            dest_path=dest,
            tweet_id=tweet_id,
        ))

    post_data: Dict = {
        "author_username": author_username,
        "author_id": author_id,
        "created_at": tweet_data.get("created_at", ""),
        "text": tweet_data.get("text", ""),
        "media_files": media_filenames,
        "quoted_tweet_id": quoted_tweet_id,
        "quoted_author": quoted_author_username,
        "quoted_text": quoted_tweet_data.get("text") if quoted_tweet_data else None,
        "quoted_created_at": quoted_tweet_data.get("created_at") if quoted_tweet_data else None,
    }

    if dry_run:
        logger.info(
            "DRY RUN: would process @%s/%s (%d media)",
            author_username, tweet_id, len(media_items),
        )
        return 0

    storage.ensure_author_directory(author_username)
    storage.save_post_content(author_username, tweet_id, post_data)

    download_stats = None
    if media_items:
        timeout = config["download"]["timeout_seconds"]
        download_stats = coordinate_downloads(media_items, timeout=timeout)

    if quoted_tweet_id and quoted_author_username:
        storage.create_quoted_symlink(
            parent_username=author_username,
            parent_post_id=tweet_id,
            quoted_username=quoted_author_username,
            quoted_post_id=quoted_tweet_id,
        )

    folder_path = str(storage.get_author_folder(author_username))
    media_count = download_stats.succeeded if download_stats else 0
    state.mark_processed(
        tweet_id,
        "success",
        [folder_path],
        media_count,
        author_username=author_username,
        author_id=author_id,
    )

    if download_stats:
        for item, result in zip(media_items, download_stats.results):
            if result.success:
                state.record_media_file(
                    tweet_id,
                    str(result.dest_path),
                    item.media_type,
                    result.file_size or 0,
                )

    symlinks_count = 1 if (quoted_tweet_id and quoted_author_username) else 0
    storage.update_author_metadata(
        author_username,
        author_id,
        posts_delta=1,
        media_delta=media_count,
        symlinks_delta=symlinks_count,
    )

    return media_count


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

        # Create directories if they don't exist
        downloads_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        logger.info("✓ Directory structure ready")

        logger.info("Setup verification complete - ready to download!")
        return True

    except Exception as e:
        logger.error(f"Setup verification failed: {e}")
        return False


def _quarantine_tweet(
    tweet_id: str,
    tweet_data: Dict,
    includes: Dict,
    exc: Exception,
    quarantine_manager: QuarantineManager,
    state: StateManager,
) -> None:
    """Quarantine a failed tweet, storing tweet+includes context for retry."""
    logger = get_logger(__name__)
    category = classify_error(exc)
    context = {"tweet": tweet_data, "includes": includes}
    quarantine_manager.quarantine_item(tweet_id, context, exc, category)
    state.mark_quarantined(tweet_id, str(exc))
    logger.warning("Quarantined tweet %s (%s): %s", tweet_id, category.value, exc)


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

    global _shutdown_requested
    _shutdown_requested = False
    old_sigterm = signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    old_sigint = signal.signal(signal.SIGINT, _handle_shutdown_signal)

    try:
        api_client = TwitterClient(config)
        state = StateManager(config)
        storage = LocalStorage(config)
        quarantine_manager = QuarantineManager(config)

        me = api_client.get_me()
        user_id = me["id"]
        logger.info("Authenticated as @%s (id=%s)", me.get("username", "?"), user_id)

        if dry_run:
            logger.info("DRY RUN mode — no files will be written")
        if limit:
            logger.info("Processing up to %d bookmarks", limit)

        processed = 0
        skipped = 0
        failed = 0
        pagination_token: Optional[str] = None

        while not _shutdown_requested:
            batch_size = min(100, limit - processed) if limit else 100

            try:
                response = api_client.get_bookmarks(
                    user_id,
                    max_results=batch_size,
                    pagination_token=pagination_token,
                )
            except RateLimitError:
                api_client.wait_for_rate_limit_reset()
                continue

            tweets = response.get("tweets") or []
            includes = response.get("includes") or {}

            if not tweets:
                logger.info("No more bookmarks to process.")
                break

            for tweet in tweets:
                if _shutdown_requested:
                    break
                if limit is not None and processed >= limit:
                    break

                tweet_id = tweet["id"]

                if state.is_already_processed(tweet_id):
                    skipped += 1
                    logger.debug("Skipping already processed tweet %s", tweet_id)
                    continue

                try:
                    media_count = _process_tweet(
                        tweet, includes, api_client, storage, state, config, dry_run=dry_run
                    )
                    processed += 1
                    logger.info(
                        "Processed tweet %s (%d media)", tweet_id, media_count
                    )
                except RateLimitError:
                    api_client.wait_for_rate_limit_reset()
                    try:
                        media_count = _process_tweet(
                            tweet, includes, api_client, storage, state, config, dry_run=dry_run
                        )
                        processed += 1
                    except Exception as retry_exc:
                        _quarantine_tweet(
                            tweet_id, tweet, includes, retry_exc,
                            quarantine_manager, state
                        )
                        failed += 1
                except Exception as exc:
                    _quarantine_tweet(
                        tweet_id, tweet, includes, exc,
                        quarantine_manager, state
                    )
                    failed += 1

            pagination_token = response.get("next_token")
            if not pagination_token:
                break

        logger.info(
            "Download complete: %d processed, %d skipped, %d failed",
            processed, skipped, failed,
        )
        print(f"\nDownload summary:")
        print(f"  Processed: {processed}")
        print(f"  Skipped:   {skipped}")
        print(f"  Failed:    {failed}")

        state.close()
        return True

    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        return False
    finally:
        signal.signal(signal.SIGTERM, old_sigterm)
        signal.signal(signal.SIGINT, old_sigint)


def show_stats(config) -> bool:
    """Display processing statistics.

    Returns:
        True if successful, False otherwise
    """
    logger = get_logger(__name__)

    try:
        state = StateManager(config)
        stats = state.get_processing_stats()
        state.close()

        print("Processing Statistics")
        print("=====================")
        print(f"Processed:    {stats.total_processed}")
        print(f"Failed:       {stats.total_failed}")
        print(f"Quarantined:  {stats.total_quarantined}")
        print(f"Media Files:  {stats.total_media_downloaded}")
        if stats.last_run_at:
            print(f"Last Run:     {stats.last_run_at}")
        else:
            print("Last Run:     (never)")
        return True

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}", exc_info=True)
        return False


def _reprocess_tweet(tweet_data: Dict) -> None:
    """Process a single tweet's data for download. Implemented in Phase 8."""
    raise NotImplementedError("reprocess logic not yet implemented; see Phase 8")


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
        quarantine_manager = QuarantineManager(config)
        state_manager = StateManager(config)
        bookmark_client = TwitterClient(config)

        quarantined = state_manager.get_quarantined_bookmarks(limit if limit is not None else 100)
        logger.info("Found %d quarantined items to retry", len(quarantined))

        results = []
        for item in quarantined:
            tweet_id = item["tweet_id"]
            retry_count = item.get("retry_count", 0)
            tweet_data = None
            exc = None

            # Try stored JSON first
            stored_data = quarantine_manager.get_tweet_data(tweet_id)
            if stored_data is not None:
                try:
                    _reprocess_tweet(stored_data)
                    tweet_data = stored_data
                except Exception as e:
                    exc = e
                    tweet_data = stored_data

            # Fall back to API if no stored data or reprocess failed
            if stored_data is None or exc is not None:
                try:
                    fresh_data = bookmark_client.get_tweet_details(tweet_id)
                    tweet_data = fresh_data
                    exc = None
                    _reprocess_tweet(fresh_data)
                except Exception as e:
                    exc = e

            if exc is None:
                quarantine_manager.remove_item(tweet_id)
                state_manager.mark_processed(tweet_id, "success", [], 0)
                results.append({
                    "tweet_id": tweet_id,
                    "outcome": "success",
                    "retry_count": retry_count,
                })
                logger.info("Successfully reprocessed %s", tweet_id)
            else:
                category = classify_error(exc)
                quarantine_manager.quarantine_item(tweet_id, tweet_data, exc, category, retry_count + 1)
                state_manager.mark_quarantined(tweet_id, str(exc), retry_count + 1)
                results.append({
                    "tweet_id": tweet_id,
                    "outcome": "failed",
                    "error": str(exc),
                    "error_category": category.value,
                    "retry_count": retry_count + 1,
                })
                logger.warning("Failed to reprocess %s: %s", tweet_id, exc)

        succeeded = sum(1 for r in results if r["outcome"] == "success")
        failed = sum(1 for r in results if r["outcome"] == "failed")
        report_path = quarantine_manager.generate_report(results)

        print(f"Quarantine retry: {len(results)} items")
        print(f"  Succeeded: {succeeded}")
        print(f"  Failed:    {failed}")
        print(f"  Report:    {report_path}")

        state_manager.close()
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
        logger.info(f"Clearing entries older than {older_than_days} days...")
        state = StateManager(config)
        cleared = state.clear_old_entries(days=older_than_days)
        state.close()
        logger.info(f"Cleared {cleared} old entries.")
        print(f"Cleared {cleared} old entries.")
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
            success = clear_cache(config)
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
        logger.error(f"Fatal error: {e}")
        return 1


def cli():
    """CLI entry point (for console_scripts in setup.py)."""
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
