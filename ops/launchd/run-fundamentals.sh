#!/bin/bash
# Quarterly wrapper: refresh constituent snapshot caches for the Monitor set.
# Calls `irc monitor snapshot` (the typed per-fund path — NOT the broad-index path).
# StandardOut/ErrPath are /dev/null (provenance-xattr fix); we write our own log.
#
# __UV_BIN__ is substituted by install.sh with the absolute path to uv.
# __REPO_ROOT__ is substituted by install.sh with the absolute repo root.
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

# Fresh per-run log (launchd writes to /dev/null). Retain ~14 days.
LOG_FILE="outputs/_logs/run-fundamentals.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-fundamentals.*.log' -type f -mtime +14 -delete 2>/dev/null || true

echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] quarterly monitor snapshot refresh"
"$UV_BIN" run irc monitor snapshot
