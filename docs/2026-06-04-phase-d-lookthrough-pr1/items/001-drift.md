Verdict: PASS

Subagent: sonnet
Plan checklist items: 20 tasks (Tasks 1–20), each with 4–7 steps
Verified present in diff: 20 / 20

---

## Drift findings

- **Task 7 / Step 3 — test weight correction + new mega-cap test** — divergent-but-accepted
  Evidence: `tests/opportunity/test_lookthrough_valuation.py` — `test_per_date_renormalization_with_shorter_history` uses `HoldingWeight("A", 45.0)` / `HoldingWeight("B", 45.0)` (not 25/25 as in the original plan draft); new test `test_per_date_floor_is_nav_fraction_not_covered_basket` added.
  The implementation code (Task 7 Step 3) correctly uses `present_ratio = sum(wb.values()) / 100.0` (NAV fraction, §3.2 units) throughout. The original plan test with weights 25/25 was inconsistent with that code — it would have required a covered-basket-fraction denominator, inverting the §3.4 mega-cap protection. The annotation "Correction applied during impl (commit bde87fa)" appears inline in the plan. Code matches the plan code exactly. Classified as **PASS** — the plan is the source of truth, the test correction matches it.
  Action: plan amended inline (annotation committed).

- **Task 8 / Step 3 — gate-ownership inversion (divergence B)** — divergent-but-accepted with rationale
  Evidence: `src/irc/opportunity/lookthrough_valuation.py` lines 20–31: `MIN_PE_POINTS = 120`, `MIN_PE_DAYS = 180`, `_pe_series_is_mature` defined here. `src/irc/opportunity/inputs_loader.py` lines 18–23: imports all three from `lookthrough_valuation` with `# noqa: F401` re-export comment.
  The plan's direction (import FROM `inputs_loader`) created a circular import: `inputs_loader` now imports `fund_valuation_percentile` FROM `lookthrough_valuation`, while `lookthrough_valuation` would have needed to import `_pe_series_is_mature` FROM `inputs_loader`. Inversion is a genuine functional equivalent: (i) the index path at `inputs_loader.py:183` still calls the SAME `_pe_series_is_mature` (now imported from `lookthrough_valuation`) — index/active symmetry preserved (spec §3.3); (ii) MIN_PE_POINTS==120, MIN_PE_DAYS==180 confirmed; (iii) all 116 scoped tests pass including those that import these from `inputs_loader`.
  Action: accepted with rationale (circular-import fix; functional equivalent confirmed).

- **Task 18 / Step 4 — `_band` imported from `states` rather than local `_BAND_BOUNDS`** — divergent-but-accepted
  Evidence: `src/irc/opportunity/lookthrough_diff_report.py` line 20: `from irc.opportunity.states import _band`. The plan offered a choice: "reuse `_band` if importable, else replicate locally." `_band` exists at `states.py:168`. The implementation chose the single-source-of-truth import (preferred). The module docstring notes the decision.
  Action: accepted with rationale (preferred option in plan was followed).

- **Task 7 `_aggregate_metric_series` — pd.Series index type** — incidental divergence, accepted
  Evidence: `src/irc/opportunity/lookthrough_valuation.py:154`: `pd.Series(out_val, index=pd.to_datetime(out_idx).date)` — returns `date` objects as index, not `DatetimeIndex`. The plan code said `pd.to_datetime(out_idx)`. The `_pe_series_is_mature` gate calls `pd.to_datetime(valid.index)` to reparse, which works on `date` objects. All 116 scoped tests pass, including the maturity gate tests that feed `_aggregate_metric_series` output through `_percentile_for_metric`. No behavioral divergence — the `date`-type index is compatible with `self_history_percentile`.
  Action: accepted (tests green; functionally equivalent).

---

## Spec-critical verifications (all PASS)

- **Flag default OFF in template:** `src/irc/templates/config/valuation_buckets.yaml` has `enabled: false`. Confirmed in diff.
- **Flag-off byte-identical (dormancy lock) test:** `tests/commands/test_opportunity_cmd_lookthrough_dormancy.py` — `test_flag_off_output_byte_identical_to_no_lookthrough_data` and `test_flag_off_matches_default_disabled_config` both present and passing.
- **Flag-on population test:** `tests/opportunity/test_inputs_loader_lookthrough.py` — `test_flag_on_populates_fundamental_percentile` exercises `enabled=True` and asserts `valuation_percentile_fundamental is not None`. Passing.
- **Index-path-unchanged test:** `tests/opportunity/test_inputs_loader_lookthrough.py` — `test_index_fund_path_unchanged_by_lookthrough_branch` exercises `cn_etf` with `enabled=True` and confirms no intercept. Passing.
- **H3 / SAME-3 invariant tests with flag OFF and ON:** `tests/commands/test_opportunity_cmd_h3_invariant.py` (pre-existing, unmodified) passes — the flag-off default keeps the invariants byte-identical. The original verdict flagged that no flag-ON coverage existed at the level where the valuation axis could leak.
  **RESOLVED by orchestrator (commit below):** added `tests/opportunity/test_lookthrough_invariants.py` (2 tests, mirroring the index-path precedent `test_valuation_fundamental_anchor.py::test_fundamental_block_emits_no_thesis_evidence_or_gap`). It locks spec §9's flag-on requirement at the `build_opportunity_row` level: (1) when the PE anchor agrees with NAV, the look-through slot is inert on **every** axis (valuation_state, evidence_gaps/H3, thesis_evidence/SAME-3, advisory_gaps, thesis_state byte-identical); (2) when it diverges (the intended advisory fires), valuation_state + advisory_gaps move but evidence_gaps (H3), thesis_evidence (SAME-3) and thesis_state (Policy B) stay byte-identical. Root-cause confirmed: `_structural_evidence_gaps` raises `missing_valuation_data` only when self AND vs_benchmark AND fundamental are ALL None, and the divergence code routes to `advisory_gaps` (never `evidence_gaps`) — so with NAV always present for active funds, the slot cannot move the H3 partition (spec §7 holds, "exactly as for the index path").
  Action: gap CLOSED within PR1 (no longer deferred to PR2).
- **`lookthrough_valuation.py` and `lookthrough_diff_report.py` pure:** confirmed — no I/O, no DuckDB, no logging in either module. Effects only in `lookthrough_diff_cmd.py` and `fundamentals_cmd.py`. PASS.
- **No PR2 scope leaked:** VERSION is `0.9.3` (unchanged). No ADR addendum in diff. No flag-flip CHANGELOG entry. Live tests authored and confirmed skipped (2 skipped in scoped run). PASS.
- **Diff report computes regardless of flag:** `lookthrough_diff_cmd.py` does not read `active_fund_lookthrough.enabled`; `test_run_computes_regardless_of_flag` confirms. PASS.

---

## Scope-creep / incidental findings

- `docs/2026-06-04-phase-d-lookthrough-pr1/PROGRESS.md` and `items/001-plan.md` — orchestrator bookkeeping; excluded per instructions. Not drift.
- `src/irc/data/stock_valuation_ingestor.py` extracts a private `_build_params` helper (not in plan code). This is a legitimate size-budget refactor (keeps `ingest_stock_valuation_history` under 20 lines). Not scope-creep.

---

## Evidence anchors for divergences A and B

- **A confirmed PASS:** `src/irc/opportunity/lookthrough_valuation.py:147–148` — `present_ratio = sum(wb.values()) / 100.0`. Plan code Step 3 matches. Test weights corrected to 45/45. Not re-flagged.
- **B confirmed accepted:** `src/irc/opportunity/inputs_loader.py:18–23` — imports from `lookthrough_valuation` with `# noqa: F401`. Index path at line 183 calls the same `_pe_series_is_mature`. MIN_PE_POINTS==120, MIN_PE_DAYS==180. All tests green. Not re-flagged.
