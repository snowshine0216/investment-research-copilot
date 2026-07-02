# MASTER-SPEC — Monitor CN-egress data-plane light-up

**Mode:** spec (single grilled feature spec; user decisions §9 locked 2026-07-02)
**Input:** `docs/superpowers/specs/2026-07-02-monitor-cn-egress-data-plane-lightup-design.md` (landed on main via spec-only PR #188, commit `cebe14eb`)
**Companion (un-shelved):** `docs/superpowers/specs/2026-06-25-monitor-flow-rank-snapshot-accumulation-design.md` (Option B2 — D-B0..B7 stand; §3 of the input records only the deltas)

## IN scope

| id | Item | Source |
|----|------|--------|
| 001 | CN-egress data-plane light-up: `IRC_CN_PROXY` contract (D1/D2), industry-leg raw fetchers via `em_raw.py` (D3/D4), batch-first flow B2 un-shelved (D5), 15:45 `flow-capture` job + hybrid schedule (D6), seed-then-organic warm-up (D7), valuation backfill routing (D8), eval schema bump + `flow_source` (D9), per-symbol flow retired from run path (D10); ADR 0019/0020 addenda; CONTEXT.md *Flow freshness state* as-built rewrite | input spec §3–§8, copied verbatim to `items/001-spec.md` |

## OUT scope

None declared beyond the input's own §4 "Out" / §10 follow-ups (report-v3 readability, `irc scout`, full-basket flow coverage, TTL industry-map caching, fund-plane/legulegu proxy routing, weight/band changes) — those are the spec's declared non-goals, not skipped items.
