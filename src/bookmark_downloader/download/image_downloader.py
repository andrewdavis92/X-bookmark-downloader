"""HTTP image downloader for X-native photos."""

from pathlib import Path

import httpx

from bookmark_downloader.download.types import DownloadResult


def download_image(url: str, dest_path: Path, tweet_id: str, timeout: int = 60) -> DownloadResult:
    tmp_path = dest_path.with_suffix(".tmp")
    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
            if not (200 <= response.status_code < 300):
                return DownloadResult(
                    url=url,
                    dest_path=dest_path,
                    success=False,
                    file_size=0,
                    error=f"HTTP {response.status_code}",
                    attempts=1,
                )
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
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
    except Exception as e:
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
