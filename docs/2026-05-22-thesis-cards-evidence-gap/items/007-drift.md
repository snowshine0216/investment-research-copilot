# Item 007 drift check verdict

**Verdict:** PASS-WITH-NOTES
**Run timestamp:** 2026-05-23
**Branch:** autodev/thesis-evidence-007-memo-and-discipline-renderers
**Base:** autodev/thesis-cards-evidence-gap

---

## File-touch map check

| Plan-expected file | Actual status | Delta |
|---|---|---|
| `src/irc/fundamentals/types.py` (M) | M | ✅ |
| `src/irc/fundamentals/snapshot_cache.py` (M) | M | ✅ |
| `src/irc/commands/memo_cmd.py` (M) | M | ✅ |
| `src/irc/memo/evidence_pool.py` (M) | M | ✅ |
| `src/irc/memo/numeric_audit.py` (M) | M | ✅ |
| `src/irc/memo/markers.py` (A) | A | ✅ |
| `src/irc/memo/aliases.py` (A) | A | ✅ |
| `src/irc/opportunity/report.py` (M) | M | ✅ |
| `src/irc/commands/opportunity_cmd.py` (M) | M | ✅ |
| `tests/memo/test_markers.py` (A) | A | ✅ |
| `tests/memo/test_aliases.py` (A) | A | ✅ |
| `tests/memo/test_same_3_invariant.py` (A) | A | ✅ |
| `tests/memo/test_determinism.py` (A — plan said `test_determinism.py`) | A | ✅ |
| `tests/opportunity/test_report_appendix.py` (A) | A | ✅ |
| `tests/commands/test_memo_cmd_aliases.py` (A) | A | ✅ |
| `tests/memo/test_evidence_pool.py` (M) | M | ✅ |
| `tests/memo/test_numeric_audit.py` (M) | M | ✅ |
| `tests/opportunity/test_report.py` (M) | M | ✅ |
| `tests/commands/test_opportunity_cmd.py` (M) | M | ✅ |
| `tests/fundamentals/test_types.py` (M) | M | ✅ |
| `tests/fundamentals/test_snapshot_cache.py` (M) | M | ✅ |
| `tests/memo/test_pick_rows.py` (M) | M | ✅ |
| `src/irc/memo/citation_selector.py` (not in plan) | M (re-export shim) | ⚠️ deviation — accepted (see §Accepted divergences) |
| `src/irc/opportunity/citation_selector.py` (not in plan) | A (new canonical) | ⚠️ deviation — accepted (see §Accepted divergences) |
| `docs/adr/0001-citation-data-model.md` (not in plan) | M (amended §3) | ⚠️ deviation — accepted (see §Accepted divergences) |
| `docs/2026-05-22-thesis-cards-evidence-gap/PROGRESS.md` | M | minor bookkeeping |

All 22 plan-expected touches are present. Three unplanned modifications exist and are all justified by the cycle-fix (`d01077f`) plus ADR amendment.

---

## Per-task verification

**T1 — Promote `_evidence_from_dict` → `@classmethod ThesisEvidence.from_dict`**
✅ Matches plan exactly. `types.py` gains the classmethod with `expected_id` mismatch guard. Four tests added to `test_types.py` (happy path, missing optional fields, holding_weight carried, citation_id mismatch raises). Commit: `81edd60`.

**T2 — Collapse `_evidence_from_dict` call sites onto `ThesisEvidence.from_dict`**
✅ Matches plan. Both `snapshot_cache.py` and `memo_cmd.py` collapse to 2-line delegator shims. Regression tests added in `test_snapshot_cache.py` and `test_pick_rows.py`. Commit: `de58573`.

**T3 — Create `src/irc/memo/markers.py`**
✅ Matches plan exactly. `REF_MARKER_FMT`, `STOCK_MARKER_FMT`, `format_ref_marker`, `format_stock_marker`, `format_combined_marker` all present with identical locked grammar. Empty-raises, stock-omit-when-None behaviour confirmed. 9 tests in `test_markers.py`. Commit: `dd79263`.

**T4 — Create `src/irc/memo/aliases.py`**
✅ Matches plan. `InstrumentAliases`, `ConstituentAliases`, `InstrumentAliasCollisionError`, `build_alias_maps` all present. Collision detection at build time; multi-owner constituent accumulates into frozenset; empty alias key skipped. 9 tests in `test_aliases.py`. Commit: `e403389`.

**T5 — Add `find_uncited_conclusions` stub**
✅ Matches plan. Stub added to `numeric_audit.py` with exact empty-map `RuntimeError` text `"empty instrument_aliases — D1c build_alias_maps did not run or returned an empty map; refusing to silent-no-op the audit"`. Returns `[]` otherwise. Two new tests in `test_numeric_audit.py`. Commit: `7921889`.

**T6 — Extend `build_evidence_pool` with citation-line emission (D1a)**
✅ Matches plan (Option β). `_format_citation_line` and `_format_citation_lines_for_row` helpers added. `select_citations(evidence, cap=3)` called at both `plan_trades`-ordered and remaining-rows loops. `[stock:{symbol}]` emitted only for `scope == "constituent"`; URL parenthetical omitted when `url == ""`. 6 new tests. Commit: `6c4a5d2`.

**T7 — Wire `memo_cmd.py::run_memo` to dataclass-form evidence + alias builder**
✅ Matches plan. `ThesisEvidence.from_dict` reconstruction loop added before `build_evidence_pool` call. `build_alias_maps` called via `_reconstruct_opportunity_rows`. Both imports present. Smoke-test in `test_memo_cmd_aliases.py` passes. Commit: `fa46029`.

**T8 — Add `_render_thesis_evidence_bullets` and wire into `_render_section` (D3a)**
✅ Matches plan. Helper added before `_render_section`. Format is `  - [ref:{cid}] {type} · {source} · {date}` (no summary, no URL — locked). `select_citations(thesis_evidence, cap=3)` used. `_render_section` extended with `lines.extend(_render_thesis_evidence_bullets(r.thesis_evidence))`. 3 new tests. Commit: `8925988`.

**T9 — Add `_render_inline_holdings_block` and wire into `_render_section` (D3b inline top-5)**
✅ Matches plan. `TOP_5_HOLDINGS_INLINE_CAP = 5`, `INLINE_HEADER_LITERAL = "持仓 (Top 5)"` constants present. `_rank_constituents_by_weight`, `_format_inline_constituent_line`, `_render_inline_holdings_block` all present with correct precedence rules. `_render_section` extended with inline block call after thesis bullets. 5 new tests. Commit: `b17ff67`.

**T10 — Add `## 持仓明细` appendix + `_APPENDIX_LINE_RE` constant**
✅ Matches plan. `_APPENDIX_LINE_RE` module-level constant present with correct 5-shape regex. `_format_appendix_constituent_line` uses first-match precedence (audit_errors first, then evidence+failures, then failure-only, then evidence-only, then defensive fallback). `_render_appendix_subsection`, `_order_publishable_rows_for_appendix`, `_render_appendix_section` all added. `compose_discipline_markdown` gains `publishable_rows` and `pick_order_iids` keyword-only params with empty defaults. 15 tests in `test_report_appendix.py`. Commit: `e755a2f`.
⚠️ **Minor note:** Plan named the Shape 1 group `failures` but implementation uses `failures_partial` — functionally equivalent, item 009 reads whichever named group the regex exposes. Not a FAIL (no AC failure; the regex still parses correctly).

**T11 — (OQ2) Stamp `audit_errors` on publishable constituent_analyses**
✅ Matches plan. `_stamp_audit_errors_from_verdict` helper added to `opportunity_cmd.py`. Called in `_build_rows` only on publishable path (no `gap_codes`). Pure `dataclasses.replace` pattern; no mutation of cached JSON. Two tests added (`test_build_rows_stamps_audit_errors_from_publishable_verdict_coverage`, `test_stamp_audit_errors_no_op_when_coverage_empty`). Commit: `4083142`.

**T12 — (Q10) Wire `_write_opportunity_outputs` to pass `publishable_rows` + `pick_order_iids`**
✅ Matches plan. `_load_pick_order_iids(out_dir)` helper added (reads `trade_plan.yaml`, returns empty tuple on missing file). `_write_opportunity_outputs` Step 5 now passes `publishable_rows=tuple(publishable_rows)` and `pick_order_iids=pick_order_iids` to `compose_discipline_markdown`. Integration test `test_write_opportunity_outputs_loads_trade_plan_for_pick_order` added. Commit: `04f43e3`.
⚠️ **Minor note:** Plan specified `import yaml` at module top; implementation uses `import yaml as _yaml` inside the function body. Functionally equivalent (avoids unused top-level import when function is never called). Not a FAIL.

**T13 — SAME-3 invariant regression test**
✅ Matches plan. `test_same_3_invariant.py` creates three tests: picks-table ↔ evidence-pool, picks-table ↔ discipline section, and `select_citations` shuffle invariant. All three pass. Commit: `be50554`.

**T14 — Two-run byte equality regression tests**
✅ Matches plan. `test_determinism.py` implements `test_evidence_pool_byte_equal_across_runs`, `test_compose_discipline_markdown_byte_equal_across_runs`, and `test_appendix_shuffled_evidence_order_byte_equal`. All three pass. Commit: `a57c4c4`.

**T15 — Final full suite green + ruff clean**
⚠️ **Partial.** The full test suite (`pytest --ignore=tests/news --ignore=tests/scoring/test_sanity_check.py -x -q`) reports 1 failure: `tests/commands/test_run_cmd.py::test_only_stage_runs_single`. This test is NOT in the item 007 file-touch map (`test_run_cmd.py` has zero diff between base and HEAD). The failure reproduces identically on the base branch `autodev/thesis-cards-evidence-gap`, confirming it is a **pre-existing failure not introduced by item 007**. Excluding it, all 208 other tests pass. Ruff reports violations in files not touched by item 007 (pre-existing: `src/irc/scoring/gold_scenarios.py`, `src/irc/decision/report.py`, etc.) plus one E741 on line 86 of `tests/memo/test_evidence_pool.py` that is in an unchanged context line pre-dating item 007. The ruff cleanup commit `fab3b08` addressed item 007's own E402/E741/F401/F841 issues correctly.

---

## AC coverage check

| AC | Description | Coverage |
|---|---|---|
| 1 | `[ref:...]` markers appear | ✅ `test_build_evidence_pool_emits_ref_markers` in `test_evidence_pool.py` |
| 2 | `[stock:...]` tag scope-conditional | ✅ `test_build_evidence_pool_emits_stock_marker_for_constituent_scope` |
| 3 | Old `[ref:filing:...]` format rejected | ✅ `test_build_evidence_pool_rejects_old_literal_ref_format` |
| 4 | URL-less line omits `({url})` | ✅ `test_build_evidence_pool_omits_empty_url_parenthetical` |
| 5 | SAME-3 invariant picks ↔ pool | ✅ `test_same_3_invariant_evidence_pool_and_picks_table` in `test_same_3_invariant.py` |
| 6 | Watchlist exclusion preserved | ✅ `test_build_evidence_pool_watchlist_excluded` |
| 7 | `build_alias_maps` correct shape | ✅ `test_build_alias_maps_instrument_aliases_basic`, `test_build_alias_maps_constituent_aliases_multi_owner` in `test_aliases.py` |
| 8 | `InstrumentAliasCollisionError` at build time | ✅ `test_build_alias_maps_instrument_collision_raises`, `test_build_alias_maps_collision_error_message_lists_iids_sorted` |
| 9 | Duplicate iid doesn't raise | ✅ `test_build_alias_maps_duplicate_iid_does_not_raise` |
| 10 | `find_uncited_conclusions` empty-map raise | ✅ `test_find_uncited_conclusions_empty_instrument_aliases_raises` in `test_numeric_audit.py` |
| 11 | Non-empty alias map no-raise | ✅ `test_find_uncited_conclusions_non_empty_aliases_does_not_raise` |
| 12 | `_render_section` 3 nested bullets | ✅ `test_render_section_emits_top_3_nested_bullets` in `test_report.py` |
| 13 | Active-fund flattened evidence used | ✅ covered via `thesis_evidence` dataclass tuple passed through in T7 wiring; SAME-3 invariant tests verify no pre-filter |
| 14 | Empty evidence → no nested bullets | ✅ `test_render_section_empty_thesis_evidence_no_bullets` |
| 15 | SAME-3 picks ↔ discipline | ✅ `test_same_3_invariant_discipline_section_matches_picks_table` |
| 16 | Inline top-5 holdings | ✅ `test_render_section_inline_top_5_holdings` |
| 17 | Inline top-5 failure rendering (❌) | ✅ `test_render_section_inline_top_5_failure_reasons_rendering` |
| 18 | Inline top-5 audit-error append (⚠️) | ✅ `test_render_section_inline_top_5_audit_errors_appended` |
| 19 | `## 持仓明细` section after `_DRAWDOWN_NOTE_CN` | ✅ `test_appendix_header_appears_after_drawdown_note` in `test_report_appendix.py` |
| 20 | Appendix lists all top-N (not just 5) | ✅ `test_appendix_lists_full_top_n_not_just_5` |
| 21 | Appendix ordering pick-row → iid-asc | ✅ `test_appendix_ordering_pick_row_order_first`, `test_appendix_ordering_non_pick_publishable_sorted_by_iid_asc` |
| 22 | Appendix per-constituent precedence | ✅ `test_appendix_shape_4_evidence_only_format`, `test_appendix_shape_2_failure_only_format`, `test_appendix_shape_3_audit_error_only_format`, `test_appendix_shape_1_evidence_plus_failures_partial_success` |
| 23 | Appendix scope = publishable only | ✅ `test_appendix_scope_publishable_only_gapped_excluded` |
| 24 | `[ref:...]` full 16 hex chars | ✅ `test_appendix_citation_id_uses_full_16_hex` |
| 25 | `select_citations` shuffle-invariant | ✅ `test_select_citations_shuffle_invariant` in `test_same_3_invariant.py`; `test_appendix_shuffled_evidence_order_byte_equal` in `test_determinism.py` |
| 26 | `memo.md` two-run byte equality | ✅ `test_evidence_pool_byte_equal_across_runs` in `test_determinism.py` |
| 27 | `discipline_report.md` two-run byte equality | ✅ `test_compose_discipline_markdown_byte_equal_across_runs` |
| 28 | Every active-fund row has appendix subsection | ✅ `test_appendix_subsection_per_publishable_row` |
| 29 | Defensive fallback (Shape 5) | ✅ `test_appendix_shape_5_defensive_fallback` |

**29/29 ACs covered.**

---

## Accepted divergences

1. **`citation_selector.py` relocation (commit `d01077f`):** The canonical `select_citations` implementation moved from `irc.memo.citation_selector` to `irc.opportunity.citation_selector`. The old path becomes a 2-line re-export shim. This was necessary to break an `opportunity → memo` import cycle created when `opportunity.report._render_section` (T8) imported the selector. The plan's file-touch map listed `src/irc/memo/citation_selector.py` as modify-in-place; the actual outcome is that module is now a shim and a new `src/irc/opportunity/citation_selector.py` holds the implementation. All existing tests continue to work through the shim. ADR 0001 §3 was amended to name the new canonical location. **Justified: no behavior change, avoids circular import.**

2. **`docs/adr/0001-citation-data-model.md` amended (unplanned file touch):** §3 updated to reflect the new canonical module path. Consistent with the cycle-fix justification above. **Justified: documentation correctness.**

3. **Named regex group `failures` vs `failures_partial` in `_APPENDIX_LINE_RE`:** Plan named the capture group `failures`; implementation uses `failures_partial`. The regex still correctly matches Shape 1 and the group content is identical. Item 009's parser will consume whichever name the constant exposes. **Minor naming deviation; no functional impact.**

4. **`_load_pick_order_iids` uses `import yaml as _yaml` inside the function body** rather than `import yaml` at the module top as the plan suggested. This avoids a module-level unused import when the function is not called. **Minor style deviation; functionally equivalent.**

5. **Pre-existing test failure `tests/commands/test_run_cmd.py::test_only_stage_runs_single`:** This test was already failing on the base branch `autodev/thesis-cards-evidence-gap` (verified by checking out the base and running the test). Item 007 did not modify `test_run_cmd.py` (zero diff). The plan's T15 says "full suite green"; this failure is pre-existing baggage from an earlier item, not a regression introduced by item 007.

---

## Blocker findings

None. The one test failure (`test_run_cmd.py::test_only_stage_runs_single`) is pre-existing on the base branch and not introduced by this item.

---

## Summary

Item 007 is fully implemented and matches the plan across all 15 tasks and 29 ACs. The single structural deviation — relocating `citation_selector.py` from `irc.memo` to `irc.opportunity` — was necessary to break a circular import and is properly documented in ADR 0001 §3. The pre-existing `test_run_cmd` failure does not indicate regression from this item. All 208 non-pre-existing tests pass; the item's own ruff violations were cleaned in `fab3b08`. Verdict: **PASS-WITH-NOTES** (cycle-fix deviation is accepted; pre-existing test failure is out of scope).
