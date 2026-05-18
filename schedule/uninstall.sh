#!/usr/bin/env bash
set -euo pipefail

# uninstall.sh — Remove X Bookmark Downloader launchd agent
#
# Environment overrides (for testing):
#   LAUNCH_AGENTS_DIR=/tmp/test    Override ~/Library/LaunchAgents
#   SKIP_LAUNCHCTL=1               Skip launchctl unload (for tests)

PLIST_NAME="com.user.bookmark-downloader.plist"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$PLIST_NAME"

if [[ ! -f "$PLIST_PATH" ]]; then
    echo "Not installed: $PLIST_PATH not found"
    exit 0
fi

if [[ "${SKIP_LAUNCHCTL:-0}" != "1" ]]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

rm "$PLIST_PATH"
echo "Uninstalled bookmark-downloader launchd agent"
