"""Tests for macOS launchd scheduling (Phase 9)."""

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SCHEDULE_DIR = REPO_ROOT / "schedule"
PLIST_PATH = SCHEDULE_DIR / "com.user.bookmark-downloader.plist"
INSTALL_SH = SCHEDULE_DIR / "install.sh"
UNINSTALL_SH = SCHEDULE_DIR / "uninstall.sh"


class TestPlistStructure:
    def test_plist_file_exists(self):
        assert PLIST_PATH.exists(), f"Plist not found: {PLIST_PATH}"

    def test_plist_is_valid_xml(self):
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        assert isinstance(plist, dict)

    def test_plist_label(self):
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        assert plist["Label"] == "com.user.bookmark-downloader"

    def test_plist_has_required_keys(self):
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        for key in ("ProgramArguments", "StartCalendarInterval",
                    "StandardOutPath", "StandardErrorPath"):
            assert key in plist, f"Missing key: {key}"

    def test_plist_program_arguments(self):
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        args = plist["ProgramArguments"]
        assert "-m" in args
        assert "bookmark_downloader" in args
        assert "download" in args

    def test_plist_schedules_three_times_daily(self):
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        schedule = plist["StartCalendarInterval"]
        assert len(schedule) == 3
        hours = {entry["Hour"] for entry in schedule}
        assert hours == {6, 14, 22}

    def test_plist_run_at_load_is_false(self):
        with open(PLIST_PATH, "rb") as f:
            plist = plistlib.load(f)
        assert plist.get("RunAtLoad") is False


@pytest.mark.skipif(
    not (REPO_ROOT / ".venv" / "bin" / "python3").exists(),
    reason="requires .venv to be set up"
)
class TestInstallScript:
    def test_install_script_exists(self):
        assert INSTALL_SH.exists()

    def test_install_creates_plist_in_target_dir(self, tmp_path):
        agents_dir = tmp_path / "LaunchAgents"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("twitter:\n  bearer_token: test\n")

        result = subprocess.run(
            ["bash", str(INSTALL_SH), "--config", str(config_path)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert (agents_dir / "com.user.bookmark-downloader.plist").exists()

    def test_install_replaces_config_placeholder(self, tmp_path):
        agents_dir = tmp_path / "LaunchAgents"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("twitter:\n  bearer_token: test\n")

        result = subprocess.run(
            ["bash", str(INSTALL_SH), "--config", str(config_path)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr

        content = (agents_dir / "com.user.bookmark-downloader.plist").read_text()
        assert "__CONFIG_PATH__" not in content
        assert str(config_path) in content

    def test_install_replaces_all_placeholders(self, tmp_path):
        agents_dir = tmp_path / "LaunchAgents"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("twitter:\n  bearer_token: test\n")

        result = subprocess.run(
            ["bash", str(INSTALL_SH), "--config", str(config_path)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr

        content = (agents_dir / "com.user.bookmark-downloader.plist").read_text()
        for placeholder in ("__PYTHON_PATH__", "__CONFIG_PATH__",
                            "__LOGS_DIR__", "__HOME__", "__PYTHON_DIR__",
                            "__PROJECT_DIR__"):
            assert placeholder not in content, f"Unreplaced placeholder: {placeholder}"

    def test_install_generated_plist_is_valid_xml(self, tmp_path):
        agents_dir = tmp_path / "LaunchAgents"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("twitter:\n  bearer_token: test\n")

        result = subprocess.run(
            ["bash", str(INSTALL_SH), "--config", str(config_path)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr

        plist_path = agents_dir / "com.user.bookmark-downloader.plist"
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
        assert plist["Label"] == "com.user.bookmark-downloader"

    def test_install_fails_without_venv(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / "LaunchAgents"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("twitter:\n  bearer_token: test\n")

        # Point to a directory with no .venv
        fake_project = tmp_path / "fake_project"
        fake_project.mkdir()
        fake_schedule = fake_project / "schedule"
        fake_schedule.mkdir()
        shutil.copy(INSTALL_SH, fake_schedule / "install.sh")
        shutil.copy(PLIST_PATH, fake_schedule / "com.user.bookmark-downloader.plist")

        result = subprocess.run(
            ["bash", str(fake_schedule / "install.sh"), "--config", str(config_path)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(fake_project),
        )
        assert result.returncode != 0


@pytest.mark.skipif(
    not (REPO_ROOT / ".venv" / "bin" / "python3").exists(),
    reason="requires .venv to be set up"
)
class TestUninstallScript:
    def test_uninstall_script_exists(self):
        assert UNINSTALL_SH.exists()

    def test_uninstall_removes_plist(self, tmp_path):
        agents_dir = tmp_path / "LaunchAgents"
        config_path = tmp_path / "config.yaml"
        config_path.write_text("twitter:\n  bearer_token: test\n")

        # Install first
        result = subprocess.run(
            ["bash", str(INSTALL_SH), "--config", str(config_path)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert (agents_dir / "com.user.bookmark-downloader.plist").exists()

        # Then uninstall
        result = subprocess.run(
            ["bash", str(UNINSTALL_SH)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0, result.stderr
        assert not (agents_dir / "com.user.bookmark-downloader.plist").exists()

    def test_uninstall_is_safe_when_not_installed(self, tmp_path):
        agents_dir = tmp_path / "LaunchAgents"
        result = subprocess.run(
            ["bash", str(UNINSTALL_SH)],
            env={**os.environ, "LAUNCH_AGENTS_DIR": str(agents_dir),
                 "SKIP_LAUNCHCTL": "1"},
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
