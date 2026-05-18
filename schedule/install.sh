#!/usr/bin/env bash
set -euo pipefail

# install.sh — Install X Bookmark Downloader as a macOS launchd agent
# Usage: ./schedule/install.sh [--config /path/to/config.yaml]
#
# Environment overrides (for testing):
#   LAUNCH_AGENTS_DIR=/tmp/test    Override ~/Library/LaunchAgents
#   SKIP_LAUNCHCTL=1               Skip launchctl load (for tests)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLIST_NAME="com.user.bookmark-downloader.plist"
LAUNCH_AGENTS_DIR="${LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}"

CONFIG_PATH=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            CONFIG_PATH="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1" >&2
            echo "Usage: $0 [--config /path/to/config.yaml]" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$CONFIG_PATH" ]]; then
    CONFIG_PATH="$PROJECT_DIR/config.yaml"
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
    echo "Error: config file not found at $CONFIG_PATH" >&2
    echo "Copy config.example.yaml to config.yaml and fill in your credentials." >&2
    exit 1
fi

PYTHON_PATH="$PROJECT_DIR/.venv/bin/python3"
if [[ ! -f "$PYTHON_PATH" ]]; then
    echo "Error: Virtual environment not found at $PROJECT_DIR/.venv" >&2
    echo "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ." >&2
    exit 1
fi

PYTHON_DIR="$(dirname "$PYTHON_PATH")"
LOGS_DIR="$HOME/Library/Logs/bookmark-downloader"

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$LOGS_DIR"

sed \
    -e "s|__PYTHON_PATH__|$PYTHON_PATH|g" \
    -e "s|__CONFIG_PATH__|$CONFIG_PATH|g" \
    -e "s|__LOGS_DIR__|$LOGS_DIR|g" \
    -e "s|__HOME__|$HOME|g" \
    -e "s|__PYTHON_DIR__|$PYTHON_DIR|g" \
    -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    "$SCRIPT_DIR/$PLIST_NAME" > "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

if [[ "${SKIP_LAUNCHCTL:-0}" != "1" ]]; then
    launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true
    launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_NAME"
fi

echo "Installed bookmark-downloader launchd agent"
echo "  Schedule: 6:00 AM, 2:00 PM, 10:00 PM daily"
echo "  Config:   $CONFIG_PATH"
echo "  Logs:     $LOGS_DIR/launchd.{out,err}.log"
echo ""
echo "Commands:"
echo "  Check status:  launchctl list | grep bookmark-downloader"
echo "  Run now:       launchctl start com.user.bookmark-downloader"
echo "  Uninstall:     $SCRIPT_DIR/uninstall.sh"
