#!/bin/bash
# Daily launchd wrapper: skip non-trading days, run the FULL pipeline, notify.
# Fail-fast: one pipeline command, capture $? once, one notify-status call.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

# Trading-day gate (UTC+8): skip Sat/Sun and dates listed in the holiday YAML.
TODAY="$(TZ='Asia/Shanghai' date +%Y-%m-%d)"
DOW="$(TZ='Asia/Shanghai' date +%u)"  # 1=Mon … 7=Sun
HOLIDAYS_FILE="config/cn_market_holidays.yaml"
if [ "$DOW" -ge 6 ]; then
  echo "[$TODAY] weekend — skipping daily run."
  exit 0
fi
if [ -f "$HOLIDAYS_FILE" ] && grep -q "$TODAY" "$HOLIDAYS_FILE"; then
  echo "[$TODAY] CN holiday — skipping daily run."
  exit 0
fi

rc=0
uv run irc run || rc=$?
uv run irc notify-status --run-kind daily --last-exit-code "$rc"
