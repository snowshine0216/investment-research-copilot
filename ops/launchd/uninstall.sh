#!/bin/bash
# Idempotent uninstall: bootout each LaunchAgent and remove its plist.
set -euo pipefail

DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=("com.irc.daily" "com.irc.weekly-full")

for label in "${LABELS[@]}"; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$DEST_DIR/$label.plist"
  echo "removed $label"
done

echo "Done."
