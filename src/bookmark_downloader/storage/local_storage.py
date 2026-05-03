"""Local file system storage for X bookmark downloader."""

import re
import unicodedata
from pathlib import Path

from bookmark_downloader.config import Config


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
