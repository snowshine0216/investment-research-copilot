#!/bin/bash
# Daily launchd wrapper: skip non-trading days, run the FULL pipeline, notify.
# Fail-fast: one pipeline command, capture $? once, one notify-status call.
#
# __UV_BIN__ is substituted by install.sh with the absolute path to uv.
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
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
if [ -f "$HOLIDAYS_FILE" ] && grep -Eq "^[-[:space:]]*[\"']?${TODAY}[\"']?[[:space:]]*$" "$HOLIDAYS_FILE"; then
  echo "[$TODAY] CN holiday — skipping daily run."
  exit 0
fi

_TIMEOUT="${IRC_RUN_TIMEOUT:-7200}"  # seconds; default 2 h
rc=0
"$UV_BIN" run irc run &
_PID=$!
_ELAPSED=0
_KILLED=0
while kill -0 "$_PID" 2>/dev/null; do
  if [ "$_ELAPSED" -ge "$_TIMEOUT" ]; then
    echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d %H:%M)] watchdog: pipeline timed out after ${_TIMEOUT}s — killing $_PID" >&2
    kill -TERM "$_PID" 2>/dev/null || true
    sleep 5
    kill -KILL "$_PID" 2>/dev/null || true
    _KILLED=1
    break
  fi
  sleep 10
  _ELAPSED=$((_ELAPSED + 10))
done
if [ "$_KILLED" -eq 1 ]; then
  rc=124
else
  wait "$_PID"
  rc=$?
fi
"$UV_BIN" run irc notify-status --run-kind daily --last-exit-code "$rc"
