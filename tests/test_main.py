"""Tests for main CLI application."""

import os
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from bookmark_downloader.main import main, verify_setup


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

    def test_verify_setup_missing_token(self, clean_env):
        """Test verify_setup with missing bearer token."""
        from bookmark_downloader.config import Config

        with pytest.raises(ValueError, match="TWITTER_BEARER_TOKEN not set"):
            Config()


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
            with patch.object(sys, "argv", ["bookmark_downloader", "download", "--help"]):
                main()

        captured = capsys.readouterr()
        assert "limit" in captured.out.lower()
        assert "dry-run" in captured.out.lower()

    def test_retry_quarantine_help(self, capsys):
        """Test retry_quarantine command help."""
        with pytest.raises(SystemExit):
            with patch.object(sys, "argv", ["bookmark_downloader", "retry_quarantine", "--help"]):
                main()

        captured = capsys.readouterr()
        assert "limit" in captured.out.lower()


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
