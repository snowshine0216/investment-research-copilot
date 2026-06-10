#!/bin/bash
# Idempotent install: template the repo path into the plists, copy to
# ~/Library/LaunchAgents, then bootout-then-bootstrap each LaunchAgent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC_DIR="$REPO_ROOT/ops/launchd"
DEST_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
LABELS=("com.irc.daily" "com.irc.weekly-full")

mkdir -p "$DEST_DIR"
mkdir -p "$REPO_ROOT/outputs/_logs"

for label in "${LABELS[@]}"; do
  src="$SRC_DIR/$label.plist"
  dest="$DEST_DIR/$label.plist"
  sed "s#__REPO_ROOT__#$REPO_ROOT#g" "$src" > "$dest"
  plutil -lint "$dest"
  # Idempotent: ignore "not found" on first install.
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$dest"
  echo "installed $label"
done

echo "Done. Inspect with: launchctl print gui/$UID_NUM/com.irc.daily"
