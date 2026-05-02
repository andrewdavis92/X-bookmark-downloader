"""yt-dlp video and animated GIF downloader for X-native media."""

from pathlib import Path

import yt_dlp

from bookmark_downloader.download.media_handler import DownloadResult


def download_video(url: str, dest_path: Path, tweet_id: str, timeout: int = 600) -> DownloadResult:
    tmp_path = dest_path.with_suffix(".tmp")
    opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(tmp_path),
        "noplaylist": True,
        "socket_timeout": timeout,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        tmp_path.rename(dest_path)
        file_size = dest_path.stat().st_size
        if file_size == 0:
            dest_path.unlink()
            return DownloadResult(
                url=url,
                dest_path=dest_path,
                success=False,
                file_size=0,
                error="empty file",
                attempts=1,
            )
        return DownloadResult(
            url=url,
            dest_path=dest_path,
            success=True,
            file_size=file_size,
            error=None,
            attempts=1,
        )
    except yt_dlp.utils.DownloadError as e:
        return DownloadResult(
            url=url,
            dest_path=dest_path,
            success=False,
            file_size=0,
            error=str(e),
            attempts=1,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
