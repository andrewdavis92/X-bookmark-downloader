"""Tests for macOS launchd scheduling (Phase 9)."""

import os
import plistlib
import subprocess
from pathlib import Path

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
