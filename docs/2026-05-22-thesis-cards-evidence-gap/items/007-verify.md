# Item 007 /verify verdict

**Verdict:** PASS
**Project type:** non-web (Python CLI)
**Date:** 2026-05-23
**PR:** https://github.com/snowshine0216/investment-research-copilot/pull/61

## Entry-point smoke

`uv run irc opportunity --help` — CLI parses cleanly; all options present (`--output-dir`, `--limit`, `--rebuild-fundamentals`, `--repo-root`).

Live smoke (`IRC_ALLOW_STALE=1 uv run irc opportunity --output-dir /tmp/007-verify/`) was attempted but blocked by an active-fund AkShare fetch (PID 40177 held DuckDB lock and acquired `data/fundamentals/.fetch_lock_*.lock` waiting for live network data). The process never reached the output-write phase before being killed. This is the documented "missing cached evidence" case from the plan: _"If the smoke run fails because of missing cached evidence… that is NOT an item 007 verdict-blocker."_

Substitute evidence: the 737 integration tests below exercise the same code paths (evidence-pool, alias-builder, discipline renderer, appendix) against fixtures without live network I/O.

## AC walkthrough (29 ACs)

| AC | Description | Test | Status |
|----|-------------|------|--------|
| 1 | `[ref:...]` markers appear in evidence pool | `test_build_evidence_pool_emits_ref_markers` | ✅ |
| 2 | `[stock:...]` tag scope-conditional (constituent only) | `test_build_evidence_pool_emits_stock_marker_for_constituent_scope` | ✅ |
| 3 | Old `[ref:filing:...]` format rejected | `test_build_evidence_pool_rejects_old_literal_ref_format` | ✅ |
| 4 | URL-less line omits `({url})` parenthetical | `test_build_evidence_pool_omits_empty_url_parenthetical` | ✅ |
| 5 | SAME-3 invariant: picks table ↔ evidence pool | `test_same_3_invariant_evidence_pool_and_picks_table` | ✅ |
| 6 | Watchlist exclusion preserved in evidence pool | `test_build_evidence_pool_watchlist_excluded` | ✅ |
| 7 | `build_alias_maps` returns correct shape + multi-owner frozensets | `test_build_alias_maps_constituent_aliases_multi_owner`, `test_build_alias_maps_returns_dict_types` | ✅ |
| 8 | `InstrumentAliasCollisionError` raised at build time | `test_build_alias_maps_instrument_collision_raises`, `test_build_alias_maps_collision_error_message_lists_iids_sorted` | ✅ |
| 9 | Duplicate iid does not raise | `test_build_alias_maps_duplicate_iid_does_not_raise` | ✅ |
| 10 | `find_uncited_conclusions` behavior on empty alias map | `test_find_uncited_conclusions_empty_aliases_with_empty_prose_returns_empty`, `test_find_uncited_conclusions_empty_aliases_with_non_empty_prose_returns_empty` | ✅ (revised in fix-round-1; see §"Amendment" below) |
| 11 | Non-empty alias map does not raise | `test_find_uncited_conclusions_non_empty_aliases_does_not_raise` | ✅ |
| 12 | `_render_section` emits top-3 nested thesis_evidence bullets | `test_render_section_emits_top_3_nested_bullets` | ✅ |
| 13 | Active-fund flattened evidence used (no pre-filter at consumer) | `test_render_section_nested_bullet_format` (validates full tuple passthrough) | ✅ |
| 14 | Empty evidence → no nested bullets rendered | `test_render_section_empty_thesis_evidence_no_bullets` | ✅ |
| 15 | SAME-3 picks table ↔ discipline section | `test_same_3_invariant_discipline_section_matches_picks_table` | ✅ |
| 16 | Inline top-5 holdings block rendered for active-fund rows | `test_render_section_inline_top_5_holdings` | ✅ |
| 17 | Inline top-5 failure rendering (`❌`) | `test_render_section_inline_top_5_failure_reasons_rendering` | ✅ |
| 18 | Inline top-5 audit-error append (`⚠️`) | `test_render_section_inline_top_5_audit_errors_appended` | ✅ |
| 19 | `## 持仓明细` section appears after `_DRAWDOWN_NOTE_CN` | `test_appendix_header_appears_after_drawdown_note` | ✅ |
| 20 | Appendix lists full top-N (not capped at 5) | `test_appendix_lists_full_top_n_not_just_5` | ✅ |
| 21 | Appendix ordering: pick-row order first, then iid-asc | `test_appendix_ordering_pick_row_order_first`, `test_appendix_ordering_non_pick_publishable_sorted_by_iid_asc` | ✅ |
| 22 | Appendix per-constituent line precedence (evidence + failures, failure-only, audit-error, evidence-only, defensive fallback) | `test_appendix_shape_1_evidence_plus_failures_partial_success`, `test_appendix_shape_2_failure_only_format`, `test_appendix_shape_3_audit_error_only_format`, `test_appendix_shape_4_evidence_only_format` | ✅ |
| 23 | Appendix scope: publishable only (gapped rows excluded) | `test_appendix_scope_publishable_only_gapped_excluded` | ✅ |
| 24 | `[ref:...]` uses full 16 hex chars | `test_appendix_citation_id_uses_full_16_hex` | ✅ |
| 25 | `select_citations` shuffle-invariant (same citation_id set across input orderings) | `test_select_citations_shuffle_invariant`, `test_appendix_shuffled_evidence_order_byte_equal` | ✅ |
| 26 | `memo.md` (evidence pool) two-run byte equality | `test_evidence_pool_byte_equal_across_runs` | ✅ |
| 27 | `discipline_report.md` two-run byte equality | `test_compose_discipline_markdown_byte_equal_across_runs` | ✅ |
| 28 | Every active-fund row gets an appendix subsection | `test_appendix_subsection_per_publishable_row` | ✅ |
| 29 | Defensive fallback Shape 5 rendered | `test_appendix_shape_5_defensive_fallback` | ✅ |

**Total: 29/29 ACs covered. All pass.**

## Module-level smoke

All 6 import+call checks pass cleanly:

```
$ uv run python -c "from irc.memo.markers import format_combined_marker; print(format_combined_marker('a' * 16, '600519'))"
[stock:600519] [ref:aaaaaaaaaaaaaaaa]

$ uv run python -c "from irc.memo.aliases import build_alias_maps, InstrumentAliasCollisionError; print('OK')"
OK

$ uv run python -c "from irc.memo.numeric_audit import find_uncited_conclusions; print(find_uncited_conclusions('x', {}, {'a':'a'}, {}, {}))"
[]

$ uv run python -c "from irc.opportunity.citation_selector import select_citations; print('OK')"
OK

$ uv run python -c "from irc.memo.citation_selector import select_citations; print('shim OK')"
shim OK

$ uv run python -c "from irc.fundamentals.types import ThesisEvidence; print(hasattr(ThesisEvidence, 'from_dict'))"
True
```

The `irc.memo.citation_selector` re-export shim resolves correctly after the cycle-breaking relocation of `citation_selector` to `irc.opportunity.citation_selector` (commit `d01077f`).

## SAME-3 invariant smoke

```
tests/memo/test_same_3_invariant.py::test_same_3_invariant_evidence_pool_and_picks_table PASSED
tests/memo/test_same_3_invariant.py::test_same_3_invariant_discipline_section_matches_picks_table PASSED
tests/memo/test_same_3_invariant.py::test_select_citations_shuffle_invariant PASSED

3 passed in 0.06s
```

**PASS.**

## Cycle-fix smoke

```
tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports PASSED

1 passed in 0.08s
```

**PASS.** The `opportunity ↔ memo` import cycle broken by commit `d01077f` is confirmed clean.

## Ruff lint (item 007 files)

All 10 item 007 source files (`markers.py`, `aliases.py`, `numeric_audit.py`, `evidence_pool.py`, `report.py`, `types.py`, `snapshot_cache.py`, `memo_cmd.py`, `opportunity_cmd.py`, `memo/pipeline.py`) pass `ruff check` with zero violations. The 119 pre-existing ruff violations in the broader codebase are unrelated to this item.

## Full test suite

```
737 passed, 12 skipped in 91.97s (1:31)
```
All 737 tests across `tests/memo/`, `tests/opportunity/`, `tests/fundamentals/`, `tests/commands/` pass. 12 skips are live-gate tests (`@pytest.mark.live_akshare`) requiring `IRC_RUN_LIVE_AKSHARE=1` — expected.

## Summary

Item 007 is fully implemented and all 29 acceptance criteria pass via dedicated integration tests. The live `irc opportunity` smoke was blocked by missing AkShare network data (active-fund fetch lock — not a 007 regression), which is the documented substitute path. All new modules (`markers.py`, `aliases.py`) import cleanly, `ThesisEvidence.from_dict` classmethod is present, the SAME-3 invariant holds across all three rendering surfaces, the import cycle is broken, and both byte-equality regression tests pass. **Recommended action: proceed to merge PR #61.**

## Amendment (post fix-round-1)

After this verify pass, the parallel `/code-review` high-effort dispatch surfaced 7 additional findings that landed in commit `fix(007): close 7 findings from post-ship /code-review high`. Notably AC10's underlying behavior was REVISED: the original `find_uncited_conclusions` stub raised `RuntimeError` on any empty `instrument_aliases`, which crashed legitimate all-gapped runs (every opportunity row failing Policy B is a valid pipeline state). The fixed stub returns `[]` for empty/non-empty prose with empty aliases; item 009 will tighten the wiring-failure detection. Post-fix-round-1: 751 passed / 12 skipped / 0 failed. AC coverage table reflects the revised tests.
