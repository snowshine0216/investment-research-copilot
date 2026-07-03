#!/bin/bash
# Idempotent uninstall: bootout each LaunchAgent, remove its plist, and remove
# the templated wrapper scripts that install.sh copied to DEST_DIR.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=("com.irc.monitor" "com.irc.fundamentals-quarterly" "com.irc.flow-capture" "com.irc.weekly")
WRAPPERS=("run-monitor.sh" "run-fundamentals.sh" "run-flow-capture.sh" "run-weekly.sh")

for label in "${LABELS[@]}"; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$DEST_DIR/$label.plist"
  echo "removed $label"
done

for wrapper in "${WRAPPERS[@]}"; do
  rm -f "$DEST_DIR/$wrapper"
  echo "removed wrapper $wrapper"
done

# Clear the single-instance locks so a later reinstall is never blocked by a
# stale lock dir. Per-run logs (run-*.log) are left in place as run history.
rm -rf "$REPO_ROOT/outputs/_logs/.run.lock" \
       "$REPO_ROOT/outputs/_logs/.monitor.lock" \
       "$REPO_ROOT/outputs/_logs/.snapshot.lock" \
       "$REPO_ROOT/outputs/_logs/.flow-capture.lock" \
       "$REPO_ROOT/outputs/_logs/.weekly.lock"

echo "Done."
