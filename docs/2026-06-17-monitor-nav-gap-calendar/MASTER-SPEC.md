# MASTER-SPEC — monitor nav-gap trading-calendar

**Mode:** spec (single feature, N=1)
**Source:** `docs/superpowers/specs/2026-06-17-monitor-nav-gap-trading-calendar-design.md`
**Date:** 2026-06-17

## Scope

| id | item | scope | rationale |
|----|------|-------|-----------|
| 001 | Calendar-grounded `nav_quality` NAV-gap check for `irc monitor` | **IN** | Fully-authored design spec with goals, design, acceptance, constraints. Single feature. |

## OUT

None.

## Summary

Replace the `monitor_signal` NAV-gap calendar-day heuristic (PR #158) with ground truth:
a fund is caveated only when it missed CN trading days the market was actually open. Adds a
cached SSE trade-calendar fetch, a pure `_missing_trading_days` metric, a gate branch that
prefers the calendar (falling back to the PR #158 heuristic when the calendar is unavailable),
and threads the calendar through `build_eval_trace`. Bumps `eval_trace.json` `schema_version`.
