# MASTER-SPEC — launchd Wrapper Watchdog + Single-Instance Lock

**Mode:** `spec` (single feature, N=1)
**Source spec:** [`docs/superpowers/specs/2026-06-30-launchd-wrapper-watchdog-design.md`](../../superpowers/specs/2026-06-30-launchd-wrapper-watchdog-design.md) (rev-2, grill'd, merged to main via PR #180)
**Run date:** 2026-06-30

## Scope classification

| # | Item | Class | Notes |
|---|------|-------|-------|
| 001 | Restore watchdog (wall-clock process-group kill) + single-instance lock to the surviving launchd wrappers (`run-monitor.sh`, `run-fundamentals.sh`), extracted into a shared `ops/launchd/lib-run.sh`, with docs + behavioral tests | **IN** | The whole feature. See `items/001-spec.md` (verbatim copy of the merged spec). |

No OUT-scope items (SKIPPED.md empty). The spec's explicit non-goals (no `notify-status` run-kind for snapshot, no SIGTERM handler in `irc`, no GNU `timeout`, no plist/schedule change, the `.tmp.{pid}` doc nit) are recorded in the spec itself and are honored as boundaries, not separate work items.
