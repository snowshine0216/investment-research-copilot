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
# shellcheck source=ops/launchd/lib-run.sh
source ops/launchd/lib-run.sh
mkdir -p outputs/_logs

# Fresh per-run log (launchd writes to /dev/null). Retain ~14 days.
LOG_FILE="outputs/_logs/run-fundamentals.$(TZ='Asia/Shanghai' date '+%Y%m%d-%H%M%S').log"
exec >> "$LOG_FILE" 2>&1
find outputs/_logs -name 'run-fundamentals.*.log' -type f -mtime +14 -delete 2>/dev/null || true

echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] quarterly monitor snapshot refresh"

# Single-instance lock (.snapshot.lock — per-wrapper, NOT shared with the monitor
# lock: a shared lock would let an overrunning 06:00 snapshot false-skip the 12:15
# monitor for a whole day; see spec §4.3). Silent skip-on-contention.
acquire_lock "outputs/_logs/.snapshot.lock" || {
  echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] another snapshot run in progress — skipping."
  exit 0
}

# Watchdog only — PROTECTIVE-ONLY: a snapshot timeout is logged loudly (the rc=124
# watchdog line in this per-run log) but does NOT page. The snapshot has no single
# completion-sentinel artifact for a notify run-kind to test, and a killed snapshot
# is already surfaced indirectly (the next daily monitor brief degrades affected
# factors to N/A). The watchdog's value here is purely killing a stuck constituent
# socket so the process does not linger and the lock is freed. See spec §4.2.
rc=0
run_with_watchdog "${IRC_SNAPSHOT_TIMEOUT:-3600}" "$UV_BIN" run irc monitor snapshot || rc=$?
echo "[$(TZ='Asia/Shanghai' date +%Y-%m-%d)] snapshot finished rc=$rc"
exit "$rc"
