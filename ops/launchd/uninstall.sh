#!/bin/bash
# Idempotent uninstall: bootout each LaunchAgent, remove its plist, and remove
# the templated wrapper scripts that install.sh copied to DEST_DIR.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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

# Clear the single-instance lock so a later reinstall is never blocked by a stale
# lock dir. Per-run logs (run-*.log) are left in place as run history.
rm -rf "$REPO_ROOT/outputs/_logs/.run.lock"

echo "Done."
