# MASTER-SPEC — Monitor per-stock valuation + capital-flow drill-down

**Mode:** spec (single feature; N=1)
**Run date:** 2026-06-19
**Source spec:** [`docs/superpowers/specs/2026-06-18-monitor-flow-stock-drilldown-design.md`](../superpowers/specs/2026-06-18-monitor-flow-stock-drilldown-design.md)
**Feature branch:** `monitor-flow-stock-drilldown` (current; 5 design commits ahead of `main`)
**Surface:** `irc monitor`

## Scope classification

| # | Item | Class | Rationale |
|---|------|-------|-----------|
| 001 | Monitor capital-flow factor + per-stock valuation drill-down (new `flow` factor + per-stock board + standalone `drilldown.html` + eval + engine bump) | **IN** | The entire approved design spec. Ships as ONE feature branch / one landing PR (matches #166's multi-slice single-PR pattern, per spec §7). Internally 4 TDD slices. |

No OUT-scope items — single-feature spec. SKIPPED.md is empty.

## What "done" means (acceptance, condensed from the spec)

- **Slice 1 (data):** `flow_fetch.py` (edge + byte-stable parsed-row JSON cache, never raises) + `holding_metrics.py` (pure per-stock valuation + flow windows + weighted aggregate + 0.50 coverage gate). Percent-point units throughout (D3); ratio-unit canary tests at `0.01`/`0.03`.
- **Slice 2 (report):** `render_drilldown.py` (board + roll-up + standalone page) + `FundView.holding_metrics` + `monitor_cmd` writes `outputs/<date>/monitor/drilldown.html` + embeds board in card. Run-level broad-outage header note when set-wide flow coverage collapses.
- **Slice 3 (bias):** `factor_maps.flow_score`, `factors._flow` + `FactorInputs.flow` (defaulted None), `profiles` eligible+D8 weights, `signal` `flow → capital-flow` family + `valuation_flow_conflict` divergence, `CANONICAL_FACTOR_ORDER` gains `flow`. `compute_signal` unchanged.
- **Slice 4 (eval+versioning):** trace schema `"2"→"3"` + `holding_metrics` block, determinism recognition, coverage health, reconciliation oracle, `_ENGINE_VERSION "1"→"2"`, `score_forward(target_engine=…)` + `runner._target_engine` (numeric max) + `details.json.excluded_by_engine`.
- **Locked tests updated** (spec §7.1): `test_known_na_reasons` (8→10 codes), `test_profiles::test_active_cn_equity_full_vector` (5→6 eligible), `test_render_factors::test_canonical_order_is_locked` (5→6 tuple), `tests/monitor/_oracle.py::_FAMILY_OF` (+flow), `test_acceptance_eval.py:79` + `eval/test_trace.py::test_schema_version_is_2` (→"3").
- **Invariants held** (spec §6): ADR 0017 evidence isolation; new N/A reasons are `KNOWN_NA_REASONS` (non-caveating); no silent caps; size budget (modules <200, fns <20); ADR 0015 lean framing — NO imperative 买入/卖出, no target weights / deltas / per-instrument action.

## Base-dependency verification (done at intake)

#166 (valuation + heat factors) IS present on this branch base: `valuation.py` (`_stock_series_by_code`, `fund_valuation_percentile`, `percentile_to_valuation_state`), `lookthrough.py`, `heat_fetch.py` all exist; `active_cn_equity.eligible == ("trend","valuation","heat","macro_tilt","constituent")` (exactly the 5 the locked tests expect). No unmet dependency.

## Grill provenance

Grill is **pre-completed** ⏭️ (spec-mode contract). The spec was SPEC'd + grilled (2026-06-18) + reviewed twice; ADR 0019 (`docs/adr/0019-monitor-capital-flow-factor.md`) and the CONTEXT.md flow-factor glossary are already committed on this branch. The orchestrator must NOT auto-invoke grill.
