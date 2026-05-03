"""Quote post detection for X bookmark downloader."""

from typing import Optional

from bookmark_downloader.api.types import TweetData
from bookmark_downloader.utils.logger import get_logger

logger = get_logger(__name__)


def extract_quoted_tweet_id(tweet_data: TweetData) -> Optional[str]:
    quoted_id = tweet_data.get("quoted_tweet_id")
    if quoted_id:
        logger.debug("Tweet %s quotes tweet %s", tweet_data.get("id"), quoted_id)
        return quoted_id
    return None
