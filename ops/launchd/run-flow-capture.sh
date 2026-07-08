#!/bin/bash
# 15:45 FLOW-CAPTURE wrapper: append the completed-day flow batch to the series
# store.
# Best-effort data-health notify tail (ADR 0016 amendment): silent on a fully-ok
# chain, pages on rotation abstain/degradation, a capture failure, or a one-time
# abstain→ok recovery. A capture timeout (rc=124) now pages `failed` — a stale
# tomorrow-flow is exactly what that surfaces. StandardOut/ErrPath are /dev/null.
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

# Watchdog: protective. On overrun the group is killed (rc=124) but capture is
# best-effort — no page. `|| rc=$?` keeps set -e from aborting before we exit.
rc=0
run_with_watchdog "${IRC_FLOW_CAPTURE_TIMEOUT:-300}" "$UV_BIN" run irc monitor flow-capture || rc=$?
echo "[$TODAY] flow-capture rc=$rc"

# Sector rotation radar (ADR 0023 D1/§9): runs AFTER flow-capture, protective-only.
# A non-zero radar exit is LOGGED but never pages and never changes $rc (the
# flow-capture exit path is authoritative). Own watchdog; advisory command.
radar_rc=0
run_with_watchdog "${IRC_ROTATION_TIMEOUT:-300}" "$UV_BIN" run irc rotation || radar_rc=$?
echo "[$TODAY] rotation rc=$radar_rc (advisory; does not affect flow-capture rc)"

# Data-health notification (best-effort): pass the flow-capture $rc (authoritative);
# a rotation crash is caught via the missing today's rotation_radar.json sentinel.
# --no-notify-on-clean: a fully-ok 15:45 chain stays silent (no page). `|| echo`
# (not `|| true`) keeps a notifier failure from aborting under set -e while leaving
# a log breadcrumb — never a page.
"$UV_BIN" run irc notify-status --run-kind flow-capture --last-exit-code "$rc" \
  --no-notify-on-clean \
  || echo "[$TODAY] notify-status failed (rc=$?) — flow-capture rc was $rc (see above)"

exit "$rc"
