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

        txt_path.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("Saved post content for %s to %s", post_id, txt_path)
        return txt_path
