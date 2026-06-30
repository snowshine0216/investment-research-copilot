Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct entry-point exercise
Entry point exercised:
  - `bash -c 'source ops/launchd/lib-run.sh; IRC_WATCHDOG_POLL=0.2 run_with_watchdog 1 sleep 30; echo rc=$?'`
  - `run_with_watchdog 60 bash -c "exit 0"` / `exit 7` (propagation)
  - `run_with_watchdog 1 bash -c 'sleep 30 & echo $! > /tmp/gpid; wait'` (grandchild kill)
  - `acquire_lock` exercised three-way (first acquire / live-pid contention / dead-pid reclaim)
  - `grep` + `bash -n` on `run-monitor.sh`, `run-fundamentals.sh`, all `ops/launchd/*.sh`

Observed behavior:
  - AC1: watchdog kills on timeout → rc=124
    observed: `[2026-06-30 15:42:49] watchdog: timed out after 1s — killing process group 57872` on stderr; shell printed `rc=124`. Elapsed ~6s (1s timeout + 5s grace + poll 0.2s).
  - AC2: watchdog propagates real child rc on success
    observed: `run_with_watchdog 60 bash -c "exit 0"` → `rc=0`; `run_with_watchdog 60 bash -c "exit 7"` → `rc=7`. Neither 124 nor 127.
  - AC3: process-group kill takes down grandchildren
    observed: grandchild pid 57920 backgrounded via `sleep 30 & echo $! > /tmp/gpid; wait`; after watchdog fired at 1s, `kill -0 57920` returned non-zero — grandchild DEAD.
  - AC4: acquire_lock — all three sub-cases
    - first acquire: `acquire_rc=0`, `pid_in_file=57970` matches `$$`
    - live-pid contention: `acquire_rc=1` (skip)
    - dead-pid reclaim (pid 99999999): `acquire_rc=0`, new pid written
  - AC5: wrapper wiring + bash -n
    - `run-monitor.sh` line 21: `source ops/launchd/lib-run.sh` ✓
    - `run-monitor.sh` line 71: `run_with_watchdog "${IRC_MONITOR_TIMEOUT:-1800}" "$UV_BIN" run irc monitor` ✓
    - `run-monitor.sh` line 72: `"$UV_BIN" run irc notify-status --run-kind monitor --last-exit-code "$rc"` ✓
    - `run-fundamentals.sh` line 14: `source ops/launchd/lib-run.sh` ✓
    - `run-fundamentals.sh` line 39: `run_with_watchdog "${IRC_SNAPSHOT_TIMEOUT:-3600}" "$UV_BIN" run irc monitor snapshot` ✓
    - `run-fundamentals.sh`: no `notify-status` call — protective-only ✓
    - `bash -n` all 5 `ops/launchd/*.sh` files: all OK

Failures: none
