#!/bin/bash
# Weekly FULL-PIPELINE wrapper: run `irc run` (ingest → … → decision), notify.
# StandardOut/ErrPath are /dev/null (provenance-xattr fix); we write our own log.
#
# __UV_BIN__ is substituted by install.sh with the absolute path to uv.
# __REPO_ROOT__ is substituted by install.sh with the absolute repo root.
#
# Research: this wrapper does NOT force RESEARCH_ENABLED — set it in .env
# (with the search API keys) to make the weekly run research-backed.
#
# Logging: launchd's StandardOut/ErrPath are /dev/null. This wrapper writes its
# own fresh per-run log instead — a persistent launchd-owned log file gets the
# macOS com.apple.provenance xattr on first write and launchd is then DENIED
# reopening it (EX_CONFIG / 78, no fire ever again). See ops/launchd/README.md.
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
# shellcheck source=ops/launchd/lib-run.sh
source ops/launchd/lib-run.sh
mkdir -p outputs/_logs

# Fresh per-run log (launchd writes to /dev/null). Retain ~14 days.
LOG_FILE="outputs/_logs/run-weekly.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-weekly.*.log' -type f -mtime +14 -delete 2>/dev/null || true

TODAY="$(TZ='Asia/Shanghai' date +%Y-%m-%d)"

# Once-per-day idempotency: decision_report.json is the LAST stage's output —
# the only artifact proving the whole ingest→…→decision chain completed. A
# halted run leaves no decision_report.json (plus PIPELINE_HALTED.md), so the
# next fire re-runs; `irc run --resume` remains the manual same-day recovery.
SENTINEL="outputs/$TODAY/decision_report.json"
if [ -f "$SENTINEL" ]; then
  echo "[$TODAY] weekly pipeline already produced decision_report.json — skipping."
  exit 0
fi

# Single-instance lock: prevent a manual `irc run` and the scheduled fire from
# overlapping (duplicate paid LLM spend, DuckDB write contention). Separate
# from .monitor.lock on purpose — a long weekly run must never false-skip the
# daily brief. Skip-on-contention is SILENT (exit 0) — a skip is not a failure.
acquire_lock "outputs/_logs/.weekly.lock" || {
  echo "[$TODAY] another weekly run in progress — skipping."
  exit 0
}

# Watchdog: bound the run at IRC_WEEKLY_TIMEOUT (default 7200s / 2h — a normal
# research-backed run takes ~40 min; the ceiling is generous because the risk
# is an unbounded upstream socket, not slow LLM work). On overrun the whole
# process group is killed (TERM → grace → KILL) and rc=124, which
# notify-status maps to "timeout".
rc=0
run_with_watchdog "${IRC_WEEKLY_TIMEOUT:-7200}" "$UV_BIN" run irc run || rc=$?

# notify is best-effort: `|| echo` keeps a notifier failure from aborting under
# `set -e` while leaving a breadcrumb — never a silent swallow.
"$UV_BIN" run irc notify-status --run-kind weekly --last-exit-code "$rc" \
  || echo "[$TODAY] notify-status failed (rc=$?) — weekly rc was $rc (see above)"

# Weekly LLM-suite refresh (OD-3, report v4 item 001): keep monitor_impact /
# monitor_narrative fresh under STALE_AFTER_DAYS=14 so daily briefs stop
# caveating on stale suites. Best-effort by construction: runs AFTER notify (a
# hung eval can never delay paging), each bounded by its own watchdog, and
# `|| echo` keeps any failure (rc=3 env-skip, rc=5 spend-gate, rc=124 timeout)
# from aborting under `set -e`. The wrapper exits with the PIPELINE's rc.
# The `env` prefix is LOAD-BEARING: run_with_watchdog execs "$@" — a bare
# IRC_RUN_LIVE_LLM_EVAL=1 word would be exec'd as a command NAME (rc 127),
# because bash parses assignments before word expansion (RD-3).
run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1 \
  "$UV_BIN" run irc eval monitor_impact \
  || echo "[$TODAY] weekly monitor_impact eval refresh failed (rc=$?) — best-effort, not paging"
run_with_watchdog "${IRC_WEEKLY_EVAL_TIMEOUT:-900}" env IRC_RUN_LIVE_LLM_EVAL=1 \
  "$UV_BIN" run irc eval monitor_narrative \
  || echo "[$TODAY] weekly monitor_narrative eval refresh failed (rc=$?) — best-effort, not paging"
exit "$rc"
