# MASTER-SPEC — Commodity-Cyclical Valuation Guard + Sector PE Accumulate

**Mode:** spec (single-feature, N=1)
**Source spec:** [`docs/superpowers/specs/2026-06-03-commodity-cyclical-valuation-guard-design.md`](../superpowers/specs/2026-06-03-commodity-cyclical-valuation-guard-design.md)
**Run date:** 2026-06-04
**Follows:** #102 (Phase 1 fundamental-led equity valuation), ADR 0012, spec #103.

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | Commodity-cyclical valuation guard (classifier withholds directional verdict on NAV-only momentum) + reachable sector-PE anchor + accumulate-forward via csindex + min-history gate + narrative risk surfacing | **IN** | The single feature this spec describes; all sub-parts (§1 guard, §2 slug-resolution + csindex fetch/ingest, §3 min-history gate, §4 downstream safety + tests) ship as one coherent change. |

No OUT-scope items (single-feature spec).

## Explicitly out-of-scope (per spec §4 "Out of scope")

These are **not** items to skip — they are deliberately excluded from this feature's blast radius and recorded here so a fresh session does not re-add them:

- PB grounding (csindex has no PB column).
- 国证/CNI indices (csindex doesn't cover CNI; fund 160221 stays guarded).
- Proxy-indexing actively-managed resource funds (no single index → stay guarded).
- Broad-index #102 re-activation (adding broad display names to `_INDEX_NAME_TO_SLUG`) — flagged as a separate opt-in in the spec's Open items; default sector-only to keep blast radius on commodity funds.
- The opportunity-stage `FetchBudgetExceeded` halt (separate issue).

## Acceptance criteria (from spec §4 + Core invariant)

1. **Core invariant (symmetric guard):** a `theme: metals` `OpportunityInput` with `valuation_percentile_fundamental is None` returns `evidence_insufficient` for BOTH a would-be-`cheap` (low NAV pct) and a would-be-`very_expensive` (high NAV pct) input. Locked by a test in `tests/opportunity/test_states.py`.
2. **Cross-asset-class breadth:** a `qdii_global` + `theme: metals` input is guarded too (covers all 21 metals-themed rows: 20 `cn_equity_fund` + 1 `qdii_global`).
3. **PE-anchored metals fund skips the guard:** a metals input *with* a non-None PE percentile uses the existing PE rule.
4. **No regression:** a non-metals equity input keeps NAV banding.
5. **Slug resolution:** a sector **display-name** `tracked_index` resolves to a canonical slug and (with mature rows) yields a PE percentile.
6. **csindex fetcher reads `市盈率1` (PE-TTM):** csindex-shaped frame → PE from `市盈率1`, `pb=None`; a test that fails if only legulegu PE names are recognised; unknown key / failure → `None`.
7. **Second ingest leg wired** with `_SECTOR_INDEX_KEYS` + sector fetcher; non-fatal on failure.
8. **Min-history gate:** thin PE series → `None`; mature → percentile; latest-null → `None`; csi300-scale unaffected.
9. **Narrative risk surfacing (non-blocking):** `evidence_insufficient` valuation appends a `valuation_state` driver in `narrative/risk.py:_state_drivers` (H3 publishability unaffected — no new evidence gap).
10. **`CONTEXT.md`** gains the "Commodity-cyclical NAV-anchor exclusion" invariant.
11. **TDD throughout**, no live calls (live AkShare double-gated); `基金概况` never used in fetch code.
