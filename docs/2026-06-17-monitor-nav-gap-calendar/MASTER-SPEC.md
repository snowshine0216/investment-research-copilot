# MASTER-SPEC — Monitor `nav_quality` calendar-grounded NAV-gap check

**Mode:** spec (single feature, N=1)
**Source spec:** [`docs/superpowers/specs/2026-06-17-monitor-nav-gap-trading-calendar-design.md`](../superpowers/specs/2026-06-17-monitor-nav-gap-trading-calendar-design.md)
**Date:** 2026-06-17
**Owner:** Xue Yin

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | Replace the `nav_quality` calendar-day NAV-gap heuristic (PR #158) with a CN-trading-calendar–grounded `missing_trading_days` check; keep #158 as the degraded-mode fallback | **IN** | The whole spec is one cohesive feature: a new AkShare calendar fetch + cached edge loader + pure metric + gate branch + edge threading. |

No OUT-scope items — the spec's §7 explicitly lists per-market calendars, SGE/SSE gold nuances, and trailing-edge changes as **YAGNI / out of scope** (not deferred work to track).

## One-line summary

A NAV cadence gap is benign iff every day in it was a non-trading day; the check WARNs only when a fund missed trading days the SSE market was actually open. One CN A-share calendar covers all 10 monitor funds (including QDII — empirically they publish on CN trading days). PR #158's calendar-day window/threshold survive only as the fallback when the calendar is unavailable.
