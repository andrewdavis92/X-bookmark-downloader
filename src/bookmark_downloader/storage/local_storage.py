"""Local file system storage for X bookmark downloader."""

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict

from bookmark_downloader.config import Config
from bookmark_downloader.utils.logger import get_logger

logger = get_logger(__name__)


class LocalStorage:
    def __init__(self, config: Config) -> None:
        self._downloads_dir = config.get_downloads_dir()

    def _sanitize_username(self, username: str) -> str:
        name = username.lstrip("@")
        name = unicodedata.normalize("NFKD", name)
        name = name.encode("ascii", errors="ignore").decode("ascii")
        name = re.sub(r"[^A-Za-z0-9_]", "", name)
        return "@" + name

    def get_author_folder(self, username: str) -> Path:
        return self._downloads_dir / self._sanitize_username(username)

    def get_post_text_path(self, username: str, post_id: str) -> Path:
        return self.get_author_folder(username) / f"{post_id}.txt"

    def get_media_path(self, username: str, post_id: str, index: int, ext: str) -> Path:
        return self.get_author_folder(username) / f"{post_id}_{index}.{ext}"

    def get_quoted_link_path(self, username: str, post_id: str, quote_index: int) -> Path:
        return self.get_author_folder(username) / f"{post_id}_quoted_{quote_index}.link"

    def ensure_author_directory(self, username: str) -> Path:
        folder = self.get_author_folder(username)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def save_post_content(self, username: str, post_id: str, post_data: Dict) -> Path:
        folder = self.ensure_author_directory(username)
        txt_path = folder / f"{post_id}.txt"

        author_username = post_data["author_username"]
        author_id = post_data["author_id"]
        created_at = post_data.get("created_at", "")
        text = post_data["text"]
        media_files = post_data.get("media_files", [])
        quoted_tweet_id = post_data.get("quoted_tweet_id")
        quoted_author = post_data.get("quoted_author")
        quoted_text = post_data.get("quoted_text")
        quoted_created_at = post_data.get("quoted_created_at")

        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            posted = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except (ValueError, AttributeError):
            posted = created_at

        lines = [
            f"Author: @{author_username} ({author_id})",
            f"Posted: {posted}",
            f"URL: https://x.com/{author_username}/status/{post_id}",
            "",
            text,
        ]

        has_media = bool(media_files)
        has_quote = bool(quoted_tweet_id)

        if has_media or has_quote:
            lines.extend(["", "---"])

        if has_media:
            lines.append(f"Media: {len(media_files)} item{'s' if len(media_files) != 1 else ''}")
            for f in media_files:
                lines.append(f"  - {f}")

        if has_quote:
            if has_media:
                lines.append("")
            quoted_author_str = f"@{quoted_author}" if quoted_author else quoted_tweet_id
            lines.append(f"Quoted Tweet: {quoted_tweet_id} by {quoted_author_str}")
            lines.append(f"Quoted Link: {post_id}_quoted_1.link")
            lines.append("---")
            if quoted_author:
                lines.append(f"Quote Author: @{quoted_author}")
            if quoted_created_at:
                try:
                    qdt = datetime.fromisoformat(quoted_created_at.replace("Z", "+00:00"))
                    lines.append(f"Quote Posted: {qdt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                except (ValueError, AttributeError):
                    lines.append(f"Quote Posted: {quoted_created_at}")
            if quoted_text:
                lines.append(f"Quote Text: {quoted_text}")

        txt_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("Saved post content for %s to %s", post_id, txt_path)
        return txt_path

    def create_quoted_symlink(
        self,
        parent_username: str,
        parent_post_id: str,
        quoted_username: str,
        quoted_post_id: str,
        quote_index: int = 1,
    ) -> Path:
        link_path = self.get_quoted_link_path(parent_username, parent_post_id, quote_index)
        self.ensure_author_directory(parent_username)

        if link_path.exists() or link_path.is_symlink():
            logger.debug("Symlink already exists at %s, skipping", link_path)
            return link_path

        quoted_folder = self._sanitize_username(quoted_username)
        target = Path("..") / quoted_folder / f"{quoted_post_id}.txt"
        link_path.symlink_to(target)
        logger.debug("Created symlink %s -> %s", link_path, target)
        return link_path
