#!/bin/bash
# Daily MONITOR wrapper: skip non-trading days, run `irc monitor`, notify.
# StandardOut/ErrPath are /dev/null (provenance-xattr fix); we write our own log.
#
# __UV_BIN__ is substituted by install.sh with the absolute path to uv.
# __REPO_ROOT__ is substituted by install.sh with the absolute repo root.
#
# Logging: launchd's StandardOut/ErrPath are /dev/null. This wrapper writes its
# own fresh per-run log instead. Reason: when launchd points at a persistent log
# file, `uv run irc monitor` tags it with the macOS `com.apple.provenance` xattr,
# and launchd is then DENIED reopening that file on the next spawn → the job fails
# with EX_CONFIG (78) before bash runs and no scheduled fire ever executes. A
# fresh per-run file (never reopened) sidesteps the protection. See
# ops/launchd/README.md.
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

# Fresh per-run log (launchd writes to /dev/null). Retain ~14 days.
LOG_FILE="outputs/_logs/run-monitor.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-monitor.*.log' -type f -mtime +14 -delete 2>/dev/null || true

# Trading-day gate (UTC+8): skip Sat/Sun and dates listed in the holiday YAML.
TODAY="$(TZ='Asia/Shanghai' date +%Y-%m-%d)"
DOW="$(TZ='Asia/Shanghai' date +%u)"  # 1=Mon … 7=Sun
HOLIDAYS_FILE="config/cn_market_holidays.yaml"
if [ "$DOW" -ge 6 ]; then
  echo "[$TODAY] weekend — skipping monitor."
  exit 0
fi
if [ -f "$HOLIDAYS_FILE" ] && grep -Eq "^[-[:space:]]*[\"']?${TODAY}[\"']?[[:space:]]*$" "$HOLIDAYS_FILE"; then
  echo "[$TODAY] CN holiday — skipping monitor."
  exit 0
fi

# Retry-only idempotency: report.html is the atomic end-of-run success artifact.
# A failed 09:00 fire leaves none, so 13:00 retries; a completed day is skipped.
REPORT="outputs/$TODAY/monitor/report.html"
if [ -f "$REPORT" ]; then
  echo "[$TODAY] monitor already produced report.html — skipping."
  exit 0
fi

rc=0
"$UV_BIN" run irc monitor || rc=$?
"$UV_BIN" run irc notify-status --run-kind monitor --last-exit-code "$rc"
