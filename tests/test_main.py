"""Tests for main CLI application."""

import os
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from bookmark_downloader.main import main, verify_setup


def _make_config_with_paths(tmp_path):
    """Return a minimal Config-like object pointing to tmp_path."""
    from unittest.mock import MagicMock
    from pathlib import Path

    config = MagicMock()
    config.__getitem__ = MagicMock(side_effect=lambda k: {
        "twitter": {"bearer_token": "tok", "request_timeout": 30},
        "download": {"timeout_seconds": 60, "max_workers": 1},
        "processing": {"follow_quotes": True},
        "logging": {"level": "INFO"},
    }[k])
    config.get_downloads_dir.return_value = tmp_path / "downloads"
    config.get_logs_dir.return_value = tmp_path / "logs"
    config.get_database_path.return_value = tmp_path / "state.db"
    config.get_quarantine_dir.return_value = tmp_path / "quarantine"
    return config


class TestVerifySetup:
    """Test verify_setup function."""

    def test_verify_setup_success(self, clean_env):
        """Test successful setup verification."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        from bookmark_downloader.config import Config
        from bookmark_downloader.main import verify_setup

        config = Config()
        result = verify_setup(config)

        assert result is True

    def test_verify_setup_missing_token(self, sample_config_yaml):
        """Test verify_setup with missing bearer token."""
        from bookmark_downloader.config import Config
        from bookmark_downloader.main import verify_setup

        config = Config(str(sample_config_yaml))
        config.config["twitter"]["bearer_token"] = "${TWITTER_BEARER_TOKEN}"
        result = verify_setup(config)
        assert result is False


class TestCLICommands:
    """Test CLI command execution."""

    def test_help_command(self, capsys):
        """Test that help command works."""
        with pytest.raises(SystemExit) as exc_info:
            main_argv = ["--help"]
            with patch.object(sys, "argv", ["bookmark_downloader"] + main_argv):
                main()

        # --help should exit with 0
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "usage" in captured.out.lower()

    def test_verify_setup_command(self, clean_env, capsys):
        """Test verify_setup command."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.verify_setup") as mock_verify:
            mock_verify.return_value = True

            with patch.object(sys, "argv", ["bookmark_downloader", "verify_setup"]):
                exit_code = main()

            assert exit_code == 0

    def test_download_command_with_limit(self, clean_env):
        """Test download command with limit argument."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.download_bookmarks") as mock_download:
            mock_download.return_value = True

            with patch.object(sys, "argv", ["bookmark_downloader", "download", "--limit", "5"]):
                exit_code = main()

            assert exit_code == 0
            mock_download.assert_called_once()
            # Check that limit was passed
            call_args = mock_download.call_args
            assert call_args[1]["limit"] == 5

    def test_download_command_dry_run(self, clean_env):
        """Test download command with dry-run flag."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.download_bookmarks") as mock_download:
            mock_download.return_value = True

            with patch.object(sys, "argv", ["bookmark_downloader", "download", "--dry-run"]):
                exit_code = main()

            assert exit_code == 0
            call_args = mock_download.call_args
            assert call_args[1]["dry_run"] is True

    def test_unknown_command_returns_error(self, clean_env):
        """Test that unknown command returns error."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch.object(sys, "argv", ["bookmark_downloader", "invalid_command"]):
            with pytest.raises(SystemExit):
                main()

    def test_missing_bearer_token_error(self, clean_env):
        """Test error when bearer token is missing."""
        # Ensure no bearer token is set
        if "TWITTER_BEARER_TOKEN" in os.environ:
            del os.environ["TWITTER_BEARER_TOKEN"]

        with patch.object(sys, "argv", ["bookmark_downloader", "verify_setup"]):
            exit_code = main()

            assert exit_code == 1

    def test_config_file_argument(self, clean_env, temp_dir):
        """Test --config argument."""
        config_file = temp_dir / "config.yaml"
        config_file.write_text("""
twitter:
  bearer_token: test_token
""")

        with patch("bookmark_downloader.main.verify_setup") as mock_verify:
            mock_verify.return_value = True

            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                with patch.object(sys, "argv", [
                    "bookmark_downloader",
                    "verify_setup",
                    "--config",
                    str(config_file)
                ]):
                    exit_code = main()

                assert exit_code == 0
            finally:
                os.chdir(original_cwd)

    def test_log_level_override(self, clean_env):
        """Test --log-level argument."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.verify_setup") as mock_verify:
            mock_verify.return_value = True

            with patch.object(sys, "argv", [
                "bookmark_downloader",
                "verify_setup",
                "--log-level",
                "DEBUG"
            ]):
                exit_code = main()

            assert exit_code == 0

    def test_keyboard_interrupt_exit_code(self, clean_env):
        """Test that KeyboardInterrupt returns correct exit code."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.reload_config") as mock_config:
            mock_config.side_effect = KeyboardInterrupt()

            with patch.object(sys, "argv", ["bookmark_downloader", "verify_setup"]):
                exit_code = main()

            # Exit code 130 is standard for SIGINT
            assert exit_code == 130

    def test_exception_exit_code(self, clean_env):
        """Test that exceptions return exit code 1."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.reload_config") as mock_config:
            mock_config.side_effect = Exception("Test error")

            with patch.object(sys, "argv", ["bookmark_downloader", "verify_setup"]):
                exit_code = main()

            assert exit_code == 1


class TestCLIHelp:
    """Test CLI help and documentation."""

    def test_help_shows_commands(self, capsys):
        """Test that help shows all available commands."""
        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", ["bookmark_downloader", "--help"]):
                main()

        captured = capsys.readouterr()
        assert "download" in captured.out
        assert "verify_setup" in captured.out
        assert "show_stats" in captured.out
        assert "retry_quarantine" in captured.out
        assert "clear_cache" in captured.out

    def test_download_help(self, capsys):
        """Test download command help."""
        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", ["bookmark_downloader", "--help"]):
                main()
        assert "download" in capsys.readouterr().out

    def test_retry_quarantine_help(self, capsys):
        """Test retry_quarantine command help."""
        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", ["bookmark_downloader", "--help"]):
                main()
        assert "retry_quarantine" in capsys.readouterr().out


class TestDownloadCommand:
    """Test download command specifically."""

    def test_download_success(self, clean_env):
        """Test successful download command."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.download_bookmarks") as mock_download:
            mock_download.return_value = True

            with patch.object(sys, "argv", ["bookmark_downloader", "download"]):
                exit_code = main()

            assert exit_code == 0

    def test_download_failure(self, clean_env):
        """Test failed download command."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.download_bookmarks") as mock_download:
            mock_download.return_value = False

            with patch.object(sys, "argv", ["bookmark_downloader", "download"]):
                exit_code = main()

            assert exit_code == 1


class TestShowStatsCommand:
    """Test show_stats command."""

    def test_show_stats_command(self, clean_env):
        """Test show_stats command execution."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.show_stats") as mock_stats:
            mock_stats.return_value = True

            with patch.object(sys, "argv", ["bookmark_downloader", "show_stats"]):
                exit_code = main()

            assert exit_code == 0


class TestRetryQuarantineCommand:
    """Test retry_quarantine command."""

    def test_retry_quarantine_command(self, clean_env):
        """Test retry_quarantine command execution."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.retry_quarantine") as mock_retry:
            mock_retry.return_value = True

            with patch.object(sys, "argv", ["bookmark_downloader", "retry_quarantine"]):
                exit_code = main()

            assert exit_code == 0


class TestClearCacheCommand:
    """Test clear_cache command."""

    def test_clear_cache_command(self, clean_env):
        """Test clear_cache command execution."""
        os.environ["TWITTER_BEARER_TOKEN"] = "test_token"

        with patch("bookmark_downloader.main.clear_cache") as mock_clear:
            mock_clear.return_value = True

            with patch.object(sys, "argv", ["bookmark_downloader", "clear_cache"]):
                exit_code = main()

            assert exit_code == 0


class TestShowStats:
    def test_show_stats_prints_stats(self, capsys, tmp_path):
        """show_stats prints counts from StateManager."""
        from bookmark_downloader.main import show_stats
        from bookmark_downloader.storage.database import ProcessingStats

        config = _make_config_with_paths(tmp_path)
        with patch("bookmark_downloader.main.StateManager") as MockSM:
            instance = MockSM.return_value
            instance.get_processing_stats.return_value = ProcessingStats(
                total_processed=42,
                total_failed=3,
                total_quarantined=1,
                total_media_downloaded=87,
                last_run_at="2026-05-17T10:23:00",
            )
            result = show_stats(config)

        assert result is True
        out = capsys.readouterr().out
        assert "42" in out
        assert "87" in out
        assert "2026-05-17T10:23:00" in out

    def test_show_stats_no_last_run(self, capsys, tmp_path):
        from bookmark_downloader.main import show_stats
        from bookmark_downloader.storage.database import ProcessingStats

        config = _make_config_with_paths(tmp_path)
        with patch("bookmark_downloader.main.StateManager") as MockSM:
            instance = MockSM.return_value
            instance.get_processing_stats.return_value = ProcessingStats(
                total_processed=0,
                total_failed=0,
                total_quarantined=0,
                total_media_downloaded=0,
                last_run_at=None,
            )
            result = show_stats(config)

        assert result is True
        assert "never" in capsys.readouterr().out

    def test_show_stats_returns_false_on_error(self, tmp_path):
        from bookmark_downloader.main import show_stats

        config = _make_config_with_paths(tmp_path)
        with patch("bookmark_downloader.main.StateManager") as MockSM:
            MockSM.side_effect = RuntimeError("db exploded")
            result = show_stats(config)

        assert result is False


class TestClearCache:
    def test_clear_cache_returns_true_and_prints_count(self, capsys, tmp_path):
        from bookmark_downloader.main import clear_cache

        config = _make_config_with_paths(tmp_path)
        with patch("bookmark_downloader.main.StateManager") as MockSM:
            instance = MockSM.return_value
            instance.clear_old_entries.return_value = 5
            result = clear_cache(config, older_than_days=90)

        assert result is True
        assert "5" in capsys.readouterr().out

    def test_clear_cache_passes_days_to_state_manager(self, tmp_path):
        from bookmark_downloader.main import clear_cache

        config = _make_config_with_paths(tmp_path)
        with patch("bookmark_downloader.main.StateManager") as MockSM:
            instance = MockSM.return_value
            instance.clear_old_entries.return_value = 0
            clear_cache(config, older_than_days=30)

        instance.clear_old_entries.assert_called_once_with(days=30)

    def test_clear_cache_returns_false_on_error(self, tmp_path):
        from bookmark_downloader.main import clear_cache

        config = _make_config_with_paths(tmp_path)
        with patch("bookmark_downloader.main.StateManager") as MockSM:
            MockSM.side_effect = RuntimeError("boom")
            result = clear_cache(config, older_than_days=90)

        assert result is False


class TestMediaExt:
    def test_photo_jpg(self):
        from bookmark_downloader.main import _media_ext
        url = {"url": "https://pbs.twimg.com/media/ABC.jpg?format=jpg&name=large", "type": "photo"}
        assert _media_ext(url) == "jpg"

    def test_photo_png(self):
        from bookmark_downloader.main import _media_ext
        url = {"url": "https://pbs.twimg.com/media/XYZ.png", "type": "photo"}
        assert _media_ext(url) == "png"

    def test_video_mp4(self):
        from bookmark_downloader.main import _media_ext
        url = {"url": "https://video.twimg.com/ext_tw_video/123/pu/vid/360x360/abc.mp4", "type": "video"}
        assert _media_ext(url) == "mp4"

    def test_unknown_extension_returns_bin(self):
        from bookmark_downloader.main import _media_ext
        url = {"url": "https://example.com/file", "type": "photo"}
        assert _media_ext(url) == "bin"


class TestFindUser:
    def test_finds_matching_user(self):
        from bookmark_downloader.main import _find_user
        includes = {"users": [
            {"id": "111", "username": "alice", "name": "Alice"},
            {"id": "222", "username": "bob", "name": "Bob"},
        ]}
        result = _find_user("111", includes)
        assert result is not None
        assert result["username"] == "alice"

    def test_returns_none_when_not_found(self):
        from bookmark_downloader.main import _find_user
        includes = {"users": [{"id": "111", "username": "alice", "name": "Alice"}]}
        assert _find_user("999", includes) is None

    def test_returns_none_for_empty_includes(self):
        from bookmark_downloader.main import _find_user
        assert _find_user("111", {}) is None
