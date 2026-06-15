#!/bin/bash
# Weekly launchd wrapper: unconditional FULL pipeline (Saturday), then notify.
# Fail-fast: one pipeline command, capture $? once, one notify-status call.
#
# __UV_BIN__ is substituted by install.sh with the absolute path to uv.
#
# Logging: launchd's StandardOut/ErrPath are /dev/null; this wrapper writes its
# own fresh per-run log. See run-daily.sh / ops/launchd/README.md for why
# (com.apple.provenance reopen-denial → EX_CONFIG).
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
mkdir -p outputs/_logs

# Fresh per-run log (launchd writes to /dev/null). Retain ~14 days.
LOG_FILE="outputs/_logs/run-weekly.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-weekly.*.log' -type f -mtime +14 -delete 2>/dev/null || true

# Single-instance lock (shared with the daily wrapper): never start a second
# pipeline on top of one already running. Skip-on-contention; reclaim a stale lock.
TODAY="$(TZ='Asia/Shanghai' date +%Y-%m-%d)"
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
"$UV_BIN" run irc notify-status --run-kind weekly --last-exit-code "$rc"
