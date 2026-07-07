# MASTER-SPEC — data-health-notify

- **Mode:** spec (single feature; Goals/Acceptance/Constraints shape; grill pre-completed by user — §9 grill log in the spec)
- **Input:** `docs/superpowers/specs/2026-07-07-data-health-notify-design.md` (verbatim copy at `items/001-spec.md`)
- **Run dir:** `docs/2026-07-07-data-health-notify/`
- **Date:** 2026-07-07

## Items

| id | Title | Scope | Rationale |
|----|-------|-------|-----------|
| 001 | Data-health notification: surface data degradation (board-PE DARK/STALE, flow staleness, rotation abstain/degraded, macro-driver age) through `irc notify-status` with new `degraded` severity + new `flow-capture` run-kind + wrapper notify tail | **IN** | The user's grilled + locked spec; explicitly handed off to autodev in spec §10 |

No OUT items (single-task spec mode). SKIPPED.md is empty.

## Out-of-scope guards carried from the spec (§1)

- NO egress fix (no CN proxy work, no efinance switch) — source-agnostic by design.
- NO M-1/M-2 factor-level freshness work (engine age-gating, real `factor_freshness`).
- NO monitor report/schema/engine change (schema 7 locked), no memo change, no new fetches, no DuckDB access from notify.
