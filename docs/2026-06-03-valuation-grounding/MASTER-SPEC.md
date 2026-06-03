# MASTER-SPEC — Fundamental-Grounded Valuation (Phase 1)

**Mode:** spec (single feature; N=1)
**Source:** `docs/superpowers/specs/2026-06-03-fundamental-valuation-grounding-design.md`
**Date:** 2026-06-03
**Feature branch:** `feat/fundamental-valuation-grounding`

## Scope classification

| # | Item | Scope | Rationale |
|---|------|-------|-----------|
| 001 | **Phase 1 — index-valuation-percentile anchor** (top-down): data layer (1a) + classifier (1b) | **IN** | Fully specified in §4 of the design; reactivates data the code already fetches and discards; bounded blast radius (broad-index CN vehicles only); every downstream invariant preserved. |
| — | Phase 2 — holdings look-through (bottom-up, active funds) | **OUT** | §2 / §5 explicitly defer this to a separate spec ("Phase 2 is intentionally not designed in full here"). Has an unresolved open method question. → SKIPPED.md. |
| — | QDII fundamental valuation (US/HK index PE/PB) | **OUT** | §2 / §3 Q3 / §8 defer — legulegu endpoints are A-share-only; needs a US/HK index-valuation source that does not exist yet. → SKIPPED.md. |
| — | Sector-theme CN ETF coverage (半导体/医药/新能源 …) | **OUT** | §4.0 marks extending coverage to sector indices as an explicit follow-on, not Phase 1. → SKIPPED.md. |
| — | CN CPI-YoY ingest (real-yield, not nominal) | **OUT** | §3.1 R1 / §9 mark switching `real_yield_10y` from nominal-gap to true-real as a "clean follow-on, not a Phase-1 blocker". → SKIPPED.md. |
| — | Phase-1 `+1` mean-reversion risk driver for divergence | **OUT** | §3 Q4 / §6 explicitly defer — risk purely inherits the grounded valuation in Phase 1. → SKIPPED.md. |

**Phase 1 itself is a single IN-scope item.** Its two sub-phases (1a data, 1b classifier) are
build-order steps of one feature, sequenced inside `items/001-plan.md` — not separate backlog
items. They ship as one PR into the feature branch.

## Acceptance criteria (lifted from §1 Goals + §8 Test strategy)

- **AC1** — `valuation_state` for broad-index equity vehicles is decided by the **PE-TTM
  historical percentile** (`valuation_percentile_fundamental`) when present; bands use the
  existing thresholds (cheap `<.20`, reasonable_low `<.40`, fair `<.70`, expensive `<.90`,
  very_expensive `≥.90`).
- **AC2** — When `valuation_percentile_fundamental is None`, `classify_valuation` falls back to
  `valuation_percentile_self` **byte-for-byte unchanged** (the NAV-only regression suite stays
  green).
- **AC3** — `valuation_state` itself is set only by the band input (PE percentile / NAV fallback);
  the consensus-upside `fundamental_contradiction` veto is preserved and only gates the `core_dca`
  promotion (R5), never the state.
- **AC4** — A single pure detector `valuation_divergence_code(inp)` is the sole source of truth;
  `classify_valuation` uses it for the reason note (signature stays `(state, reason)`) and
  `build_opportunity_row` folds `valuation_price_fundamental_divergence` into `advisory_gaps`
  (never `evidence_gaps`; H3 + SAME-3 untouched) (R2).
- **AC5** — The earnings-yield-vs-real-yield anchor fires because `earnings_yield = 1/pe_ttm`
  (ratio) and `real_yield_10y = cn_10y_yield/100` (ratio) are both populated in ratio units (R1).
- **AC6** — `populate_inputs` performs **no live index fetch**: the `provider.fetch_index_valuation`
  call is removed; index PE/PB is read from the cached `index_valuation_history` DuckDB table
  (R3). A provider stub whose `fetch_index_valuation` raises must not be invoked by the index path.
- **AC7** — `fetch_cn_index_valuation_history` is AkShare-only ingest infra, NOT a 4th provider
  method; `CnFundamentalsProvider` stays a 3-method Protocol and its tests are untouched (R4).
- **AC8** — Risk inherits the grounded verdict with **no change** to `derive_position_risk_level`.
- **AC9** — Purity / determinism / cached-evidence invariants hold: classifiers side-effect-free,
  all network I/O in the ingest fetcher, `self_history_percentile` rank-inclusive `<30→None`.

## Constraints (from §7 + CLAUDE.md / CONTEXT.md)

- TDD: red → green; test file mirrors source.
- Pure classifiers, effects at the edges; `irc opportunity` reads cached evidence (no live fetch).
- Forbidden `基金概况` indicator must never appear in fetch code (acceptance grep test).
- Citation-ID, Policy B, dual-coverage gate, H3/SAME-3 invariants all unaffected.
