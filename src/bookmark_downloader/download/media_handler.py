"""Media download coordinator for X bookmark downloader."""

import time
from typing import List

from bookmark_downloader.download.image_downloader import download_image
from bookmark_downloader.download.video_downloader import download_video
from bookmark_downloader.download.types import DownloadResult, DownloadStats, MediaItem
from bookmark_downloader.utils.logger import get_logger

# Re-export so callers can still import from this module
__all__ = ["MediaItem", "DownloadResult", "DownloadStats", "coordinate_downloads"]

logger = get_logger(__name__)


def coordinate_downloads(items: List[MediaItem], timeout: int = 600) -> DownloadStats:
    results: List[DownloadResult] = []
    max_attempts = 3
    backoff = [2, 4]

    for item in items:
        logger.debug("Downloading %s for tweet %s", item.url, item.tweet_id)

        if item.media_type == "photo":
            download_fn = download_image
        elif item.media_type in ("video", "animated_gif"):
            download_fn = download_video
        else:
            logger.warning(
                "Unknown media_type '%s' for tweet %s, skipping",
                item.media_type,
                item.tweet_id,
            )
            results.append(DownloadResult(
                url=item.url,
                dest_path=item.dest_path,
                success=False,
                file_size=0,
                error=f"unknown media_type: {item.media_type}",
                attempts=0,
            ))
            continue

        result = None
        for attempt in range(1, max_attempts + 1):
            result = download_fn(item.url, item.dest_path, item.tweet_id, timeout)
            result.attempts = attempt
            if result.success:
                break
            if attempt < max_attempts:
                logger.warning(
                    "Attempt %d failed for %s: %s, retrying in %ds",
                    attempt,
                    item.url,
                    result.error,
                    backoff[attempt - 1],
                )
                time.sleep(backoff[attempt - 1])

        if not result.success:
            logger.error(
                "All %d attempts failed for %s: %s",
                max_attempts,
                item.url,
                result.error,
            )

        results.append(result)

    succeeded = sum(1 for r in results if r.success)
    tweet_id = items[0].tweet_id if items else ""

    logger.info(
        "Downloads complete for tweet %s: %d/%d succeeded",
        tweet_id,
        succeeded,
        len(items),
    )
    return DownloadStats(
        tweet_id=tweet_id,
        total=len(items),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )
