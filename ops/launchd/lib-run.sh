#!/bin/bash
# Shared launchd wrapper helpers — sourced by run-monitor.sh / run-fundamentals.sh
# AFTER `cd "$REPO_ROOT"` (so the relative `source ops/launchd/lib-run.sh` resolves).
#
# Pure logic, NO __UV_BIN__/__REPO_ROOT__ placeholders — checked in verbatim.
# Restores the two robustness primitives lost when run-daily.sh was deleted in the
# single-daily-12:15 schedule rework (#178). Rationale lives in
# docs/2026-06-30-launchd-watchdog/items/001-spec.md (no standalone ADR; ADR 0016
# carries a one-line pointer).

# acquire_lock <lock_dir>
#
# Atomic single-instance lock via `mkdir` (mkdir is atomic across processes).
# On success: write $$ to <lock_dir>/pid, install an EXIT trap that removes the
# dir, return 0. On contention: if the holder pid is alive return non-zero
# (caller skips); if the holder is gone, reclaim (rm -rf + retry mkdir). bash
# traps are global, but only acquire_lock installs an EXIT trap, so there is no
# trap-stacking ambiguity. The lock prevents duplicate paid LLM spend + wasted
# concurrent work (the forward ledger reader dedups, so it is bloat-not-
# contamination). See spec §3.1 / §4.3.
acquire_lock() {
  local lock_dir="$1"
  if mkdir "$lock_dir" 2>/dev/null; then
    echo "$$" > "$lock_dir/pid"
    _IRC_LOCK_DIR="$lock_dir"
    trap 'rm -rf "$_IRC_LOCK_DIR"' EXIT
    return 0
  fi
  local holder
  holder="$(cat "$lock_dir/pid" 2>/dev/null || true)"
  if [ -n "${holder:-}" ] && kill -0 "$holder" 2>/dev/null; then
    return 1   # held by a live process — caller skips
  fi
  # Holder is gone — reclaim the stale lock and retry once.
  rm -rf "$lock_dir"
  if mkdir "$lock_dir" 2>/dev/null; then
    echo "$$" > "$lock_dir/pid"
    _IRC_LOCK_DIR="$lock_dir"
    trap 'rm -rf "$_IRC_LOCK_DIR"' EXIT
    return 0
  fi
  return 1
}

# run_with_watchdog <timeout_secs> <cmd> [args...]
#
# Background <cmd args...> under bash job control so it becomes a process-group
# leader (PGID == $!), poll it on the IRC_WATCHDOG_POLL cadence using the bash
# $SECONDS wall-clock builtin, and on overrun escalate TERM -> grace -> KILL on
# the whole PROCESS GROUP (negative PID), returning 124. `uv run irc ...` spawns
# a Python child, so a single-PID kill would orphan the worker (continued paid
# spend + a late monitor.json write); the group kill takes down uv + Python +
# grandchildren in one shot. macOS-native: no GNU timeout, no setsid.
run_with_watchdog() {
  local timeout="$1"
  shift
  set -m                       # job control: backgrounded job leads its own group
  "$@" &
  local pid=$!                 # == PGID under set -m
  set +m
  SECONDS=0                    # bash wall-clock builtin; immune to system load
  local killed=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$SECONDS" -ge "$timeout" ]; then
      echo "[$(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M:%S')] watchdog: timed out after ${timeout}s — killing process group $pid" >&2
      kill -TERM -"$pid" 2>/dev/null || true   # negative PID = whole group
      sleep 5
      kill -KILL -"$pid" 2>/dev/null || true
      killed=1
      break
    fi
    sleep "${IRC_WATCHDOG_POLL:-10}"           # kill -0 check cadence (tests: 0.2)
  done
  if [ "$killed" -eq 1 ]; then
    return 124
  fi
  local rc=0
  wait "$pid" || rc=$?
  return "$rc"
}
