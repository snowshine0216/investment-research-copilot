#!/bin/bash
# Daily launchd wrapper: skip non-trading days, run the FULL pipeline, notify.
# Fail-fast: one pipeline command, capture $? once, one notify-status call.
#
# __UV_BIN__ is substituted by install.sh with the absolute path to uv.
#
# Logging: launchd's StandardOut/ErrPath are /dev/null. This wrapper writes its
# own fresh per-run log instead. Reason: when launchd points at a persistent log
# file, `uv run irc run` tags it with the macOS `com.apple.provenance` xattr, and
# launchd is then DENIED reopening that file on the next spawn → the job fails
# with EX_CONFIG (78) before bash runs and no scheduled fire ever executes. A
# fresh per-run file (never reopened) sidesteps the protection. See
# ops/launchd/README.md.
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

# Fresh per-run log (launchd writes to /dev/null). Retain ~14 days.
LOG_FILE="outputs/_logs/run-daily.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-daily.*.log' -type f -mtime +14 -delete 2>/dev/null || true

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

# Idempotency guard: a successful run today writes decision_report.md and clears
# PIPELINE_HALTED.md (run_pipeline). Skip so the redundant fire times (17:30 /
# 20:00 / 22:30) don't re-run a day that already completed; still RE-RUN if a
# prior fire halted (retry).
TODAY_DIR="outputs/$TODAY"
if [ -f "$TODAY_DIR/decision_report.md" ] && [ ! -f "$TODAY_DIR/PIPELINE_HALTED.md" ]; then
  echo "[$TODAY] pipeline already completed today — skipping (idempotent)."
  exit 0
fi

# Single-instance lock (portable, atomic mkdir): never start a second pipeline on
# top of one already running (e.g. a slow earlier fire). Skip-on-contention keeps
# launchd from piling up; a stale lock (dead holder) is reclaimed.
LOCK_DIR="outputs/_logs/.run.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  _holder="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [ -n "${_holder:-}" ] && kill -0 "$_holder" 2>/dev/null; then
    echo "[$TODAY] another irc run (pid $_holder) in progress — skipping."
    exit 0
  fi
  echo "[$TODAY] reclaiming stale lock (holder ${_holder:-?} gone)."
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" 2>/dev/null || { echo "[$TODAY] could not acquire lock — skipping."; exit 0; }
fi
echo "$$" > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

_TIMEOUT="${IRC_RUN_TIMEOUT:-7200}"  # seconds; default 2 h
rc=0
"$UV_BIN" run irc run &
_PID=$!
_ELAPSED=0
_KILLED=0
while kill -0 "$_PID" 2>/dev/null; do
  if [ "$_ELAPSED" -ge "$_TIMEOUT" ]; then
    echo "[$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M')] watchdog: pipeline timed out after ${_TIMEOUT}s — killing $_PID" >&2
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
  wait "$_PID" || rc=$?
fi
"$UV_BIN" run irc notify-status --run-kind daily --last-exit-code "$rc"
