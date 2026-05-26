Verdict: PASS

Subagent: sonnet
Items reviewed: 3
Doc changes verified:
  - CONTEXT.md — covers `ActiveFundSnapshot.fund_level_evidence` (item 001); "Foreign-heavy fund (rule 2.5 short-circuit)" section (item 001); `FOREIGN_HEAVY_THRESHOLD` constant entry (item 001); "QDII premium-to-NAV ratio" section (item 002); `fetch_qdii_premium_pct` fetcher contract (item 002); "Off-exchange synthetic-zero premium policy" (item 002); `qdii_premium_too_high` gate semantics (item 002); `qdii_max_premium_pct gt=0 invariant` (item 002); "Decision Sheet → memo §5 picks-table mirror" (item 003); `PickRow.tranche_cap_pct / PickRow.trigger_status` fields (item 003); `_format_trigger_status_compact` helper (item 003); `resolve_trigger_current_value + MACRO_FIELD_TO_KEY` relocation (item 003); `live_inputs.py` module entry (item 003)
  - docs/adr/0002 §5 F6 — covers QDII premium fetcher cross-reference (item 002); "F6 QDII premium-to-NAV fetcher" paragraph present with lru_cache pattern, degrade-to-None contract, off-exchange synthetic-zero routing, and orthogonality with 2026-05-25 QDII reform
  - docs/adr/0003 §7 — covers Policy B rule 2.5 (item 001); status header amended to "Amended 2026-05-26"; §1 rule list updated from "five rules" to "six rules" with rule 2.5 entry; full §7 section documents 50% threshold rationale, cache-shape compatibility, interaction with §5 and §6, fetch-budget impact, and trade-offs considered
  - CHANGELOG.md — three new [Unreleased] subsections present: `memo-picks-table-decision-mirror` (item 003), `qdii-premium-fetcher` (item 002), `policy-b-foreign-heavy` (item 001); all dated 2026-05-26
  - TODOS.md — 5 followups across items 001 and 002: mixed-fund stale-cache with empty `fund_level_evidence` (item 001); `_ak_call` timeout enforcement (item 001); `_EXCHANGE_FROM_SYMBOL_PREFIX` missing `"5": "SH"` (item 001); synthetic `qdii_premium_pct=0.0` display flag (item 002); `lru_cache` test isolation contributor note (item 002); item 003 added 0 (P2s were pre-existing per 003-ship-blocked.md)
Missing coverage: none
