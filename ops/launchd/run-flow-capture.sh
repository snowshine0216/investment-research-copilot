#!/bin/bash
# 15:45 FLOW-CAPTURE wrapper: append the completed-day flow batch to the series
# store, then run the sector rotation radar. A capture TIMEOUT (rc=124) now PAGES
# as `failed` via the flow-capture notify tail below (data-health-notify): a
# capture timeout means tomorrow's flow is stale, which is exactly what that
# feature surfaces. The rotation step stays advisory (its rc never pages).
# StandardOut/ErrPath are /dev/null; we write our own log.
#
# __UV_BIN__ / __REPO_ROOT__ are substituted by install.sh.
set -euo pipefail

UV_BIN="__UV_BIN__"
REPO_ROOT="__REPO_ROOT__"
cd "$REPO_ROOT"
# shellcheck source=ops/launchd/lib-run.sh
source ops/launchd/lib-run.sh
mkdir -p outputs/_logs

LOG_FILE="outputs/_logs/run-flow-capture.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-flow-capture.*.log' -type f -mtime +14 -delete 2>/dev/null || true

TODAY="$(TZ='Asia/Shanghai' date +%Y-%m-%d)"
DOW="$(TZ='Asia/Shanghai' date +%u)"
HOLIDAYS_FILE="config/cn_market_holidays.yaml"
if [ "$DOW" -ge 6 ]; then
  echo "[$TODAY] weekend — skipping flow-capture."; exit 0
fi
if [ -f "$HOLIDAYS_FILE" ] && grep -Eq "^[-[:space:]]*[\"']?${TODAY}[\"']?[[:space:]]*$" "$HOLIDAYS_FILE"; then
  echo "[$TODAY] CN holiday — skipping flow-capture."; exit 0
fi

# Single-instance lock (separate from the monitor lock).
acquire_lock "outputs/_logs/.flow-capture.lock" || {
  echo "[$TODAY] another flow-capture in progress — skipping."; exit 0
}

# Watchdog. On overrun the group is killed (rc=124) and the notify tail below
# pages it as `failed` (data-health-notify — a capture timeout ⇒ stale flow).
# `|| rc=$?` keeps set -e from aborting before we notify + exit.
rc=0
run_with_watchdog "${IRC_FLOW_CAPTURE_TIMEOUT:-300}" "$UV_BIN" run irc monitor flow-capture || rc=$?
echo "[$TODAY] flow-capture rc=$rc"

# Sector rotation radar (ADR 0023 D1/§9): runs AFTER flow-capture, protective-only.
# A non-zero radar exit is LOGGED but never pages and never changes $rc (the
# flow-capture exit path is authoritative). Own watchdog; advisory command.
radar_rc=0
run_with_watchdog "${IRC_ROTATION_TIMEOUT:-300}" "$UV_BIN" run irc rotation || radar_rc=$?
echo "[$TODAY] rotation rc=$radar_rc (advisory; does not affect flow-capture rc)"

# Data-health notification (data-health-notify; ADR 0016 amendment). Runs AFTER
# the trading-day gates (weekend/holiday `exit 0` above → no non-trading-day
# noise) and passes the flow-capture $rc (authoritative). A rotation crash is
# still surfaced because the notify sentinel is today's rotation_radar.json,
# written on BOTH the ok and abstain paths (absent only on a real crash).
# `--no-notify-on-clean`: a fully-ok 15:45 chain stays SILENT — it pages only on
# degradation/abstain/failure, plus a one-time abstain→ok recovery notice.
# Best-effort: a notifier failure is a log-only breadcrumb, never a page.
"$UV_BIN" run irc notify-status --run-kind flow-capture --last-exit-code "$rc" \
  --no-notify-on-clean \
  || echo "[$TODAY] notify-status failed (rc=$?) — flow-capture rc was $rc (see above)"
exit "$rc"
