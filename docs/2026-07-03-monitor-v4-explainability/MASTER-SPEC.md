# MASTER-SPEC — Monitor report v4 explainability

**Mode:** backlog (4 items)
**Source spec:** [docs/superpowers/specs/2026-07-03-monitor-report-v4-explainability-design.md](../superpowers/specs/2026-07-03-monitor-report-v4-explainability-design.md) — grilled + locked 2026-07-03; all open decisions (OD-1..OD-3) resolved in-session.
**Date:** 2026-07-03

## IN-scope items

IDs follow input order (spec §3 lists WS-1..WS-4); execution order is locked separately in MASTER-PLAN.md (`Item order:`).

| ID | Item | Spec decisions | Size | Summary |
|----|------|----------------|------|---------|
| 001 | WS-1 — Caveat transparency | P1 + P2 + OD-3 weekly eval refresh | small-medium | `staleness.resolve_health` age-stamps stale reasons; `eval/gate.py` caveated-branch reason assembly; chip tooltip + anchor + run-global dedupe to ONE 今日速览 line + card-level `为何有保留` only for fund-specific causes + panel remediation hint; `ops/launchd/run-weekly.sh` appends best-effort live LLM eval runs. |
| 002 | WS-2 — Macro direction + mechanism | P3 + P4 + P5 | medium | Pure join (theme × fund impacts) → colored inline-signed fund chips + legend; per-claim `attribution_strength` tags; narrative prompt 2→3 with per-theme `mechanism` clause (validator required-optional, sanitizer, live-eval corpus extension). |
| 003 | WS-3 — Divergence detail | P6 | small | New pure `divergence_caveat_detail(code, contributions)` in `render_factors.py` (static map retained as fallback); call-site swap at `render_cards.py:102`. |
| 004 | WS-4 — Industry fill | P7 + P8 (+ P9 schema bump carrier) | medium-large | `+f127` in both existing `ulist.np` batch call sites; new cross-day `industry_map_store.py` (≤30d serve-while-stale); board-PE fetch-first reorder + serve-while-stale ≤3td with age tag + freshness state; renderer + panel + docs (ADR 0020 addendum, CONTEXT.md term already landed, ops manual + diagram sync). |

Cross-cutting (owned by the item that lands it first / last):

- **Schema bump 6→7 (P9)** — ONE eval-trace `schema_version` bump covering: populated `gate.reason` (001), per-theme `mechanism` (002), `board_pe_freshness` marker (004). The first-landing item that adds a trace field carries the bump; later items must NOT bump again.
- **No `_ENGINE_VERSION` bump** (P9) — all items are render/gate-reason/prompt/data-availability class.
- **Narrative prompt version 2→3** lands with item 002.

## OUT-scope items

None — all 4 workstreams are IN. (Spec §5 non-goals — dark-factor counts in 数据健康, WS-C not-heated scout, weight/band changes, per-claim LLM direction, nav_cover backfill — are spec-level exclusions, not backlog items; recorded in SKIPPED.md for the audit trail.)

## Known risks

- **004 live spot-check:** WS-4 slice 1 requires one live f184 byte-identity spot-check through the proxy before merge. If live endpoints are unreachable at that point, the spec allows items 1–3 to land regardless; 004 pauses at its verify gate (environmental stop, documented — not silently skipped).
- **`tests/commands/` must be run per-file** — the whole dir hangs (known suite-ordering issue).
