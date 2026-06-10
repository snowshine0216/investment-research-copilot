#!/bin/bash
# Idempotent uninstall: bootout each LaunchAgent, remove its plist, and remove
# the templated wrapper scripts that install.sh copied to DEST_DIR.
set -euo pipefail

DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=("com.irc.daily" "com.irc.weekly-full")
WRAPPERS=("run-daily.sh" "run-weekly-full.sh")

for label in "${LABELS[@]}"; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$DEST_DIR/$label.plist"
  echo "removed $label"
done

for wrapper in "${WRAPPERS[@]}"; do
  rm -f "$DEST_DIR/$wrapper"
  echo "removed wrapper $wrapper"
done

echo "Done."
