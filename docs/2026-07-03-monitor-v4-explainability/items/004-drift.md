Verdict: PASS

## Subagent

Diff compared: `git diff autodev/monitor-v4-explainability-feature...claude/monitor-v4-explainability-004` (28 files, 1420 insertions / 151 deletions). All file-by-file diffs read directly (not the impl agent's summary). All plan-referenced test suites re-run live; lint scoped to touched files re-run live; freeze-pin greps re-run live.

## Plan checklist items (11 tasks, ~60 steps)

- Task 1 (`flow_batch_fetch` f127 rides the batch, AC-1/AC-2): OK. `parse_ulist`/`fetch_flow_today_batch` tuple-shape rewrite, `_coerce_industry`, `fields=f12,f14,f184,f127`, shims at `_batch_flow_industry` (renamed from `_provisional_flow_note`) and `run_flow_capture` unpack — all verbatim match. Test file rewritten with 9 tests incl. AC-1 flow-identity guard; all pass.
- Task 2 (`industry_map_store.py`, AC-4): OK. New module 90 lines, `load_store`/`merge_seen`/`fresh_slice`/`record_seen` byte-identical to plan's code block. 9 tests pass (plan said "9 passed" — matches).
- Task 3 (`board_pe_staleness.py`, AC-9/AC-10): OK. New module 113 lines, `BoardPeFreshness`/`freshness_dict`/`trading_day_age`/`read_day_table`/`write_day_table`/`newest_nonempty`/`stale_fallback` byte-identical to plan. 15 tests present and pass (plan doc says "14 passed" — **confirmed cosmetic miscount**, see Amendment below).
- Task 4 (`fetch_industry_pe` → tuple, AC-9): OK. Day-file I/O helpers moved out; `industry_valuation.py` ends at 188 lines (≤ 207 budget). Shim in `_build_full_basket_metrics` and `_patch_common` test update both present. All industry_valuation tests pass, including new FRESH/STALE/DARK/calendar-independence cases.
- Task 5 (trace + panel reason, AC-11/AC-12): OK. `build_eval_trace(board_pe_freshness=None)` additive key; `SCHEMA_VERSION` stays `"7"`, comment extended not bumped; `_board_pe_reason` + `valuation_coverage_health(..., board_pe_freshness=None)` match plan verbatim. All trace/structural tests pass.
- Task 6 (age tag on both surfaces, AC-13): OK. `board_pe_age_note_html` reuses `.na-reason` class, locked-copy text `板块PE 引用 <date> · N个交易日前` present verbatim; `drilldown_section_html`/`drilldown_page_html` row[6] threading; `FundView.board_pe_freshness` trailing-defaulted; `_drilldown_block` appends note. Golden file `tests/monitor/golden/report.html` shows **zero diff** vs. base — confirmed byte-identical, test passes.
- Task 7 (`monitor_cmd` batch-first wiring, AC-3/5/6): OK. `_full_basket_union_symbols`, `_industry_map_for` (store→batch→fallback consume order), `_record_industry_seen`, `_industry_serving_map`, all four renamed monkeypatch sites — match plan verbatim. New `tests/commands/test_monitor_cmd_industry.py` present with all AC-3/5/6 tests; passes.
- Task 8 (board-PE fetch-first, AC-8 + wiring): OK. `_wants_board_pe`, `_fetch_board_pe`, run-level hoist of `trading_days` + fetch-before-loop ordering, threading through `_process_fund`/`_make_view`/`_write_drilldown`/`_compute_gates`/`_write_eval_artifacts` — all match. Wiring tests (fetch-order recorder, hoisted-calendar, trace/report/panel end-to-end, no-active-funds skip) present and pass.
- Task 9 (`run_flow_capture` widened + P8c, AC-3/5/14): OK. Full-basket batch call, **explicit top-5 slice-back verified in code** (`store_flow = {s: flow_by_symbol.get(s) for s in top5_union}`), `_record_industry_seen` then `_capture_board_pe` strictly after `append_today` (RD-6 ordering) — matches plan. Rewritten test file has 7 tests (slice-back, industry-merge, board-PE-failure-tolerance, RD-6 ordering probe, empty-early-return, batch-failure-degrade, batch-note-no-store); all pass.
- Task 10 (docs sync, AC-17): OK. ADR 0020 addendum + CONTEXT.md terms verified pre-existing (grep count 1 each, zero diff hunks in this branch — correctly "verify only" per plan). `docs/monitor/README.md`, `docs/diagrams/monitor-workflow.html`, `CHANGELOG.md` edits match plan's specified text blocks exactly (ops-manual row + bullet + 2 data-file rows + troubleshooting row; 3 diagram label edits; CHANGELOG `[Unreleased]` block).
- Task 11 (freeze/hygiene sweep, AC-16/AC-18): OK, verified live — `_ENGINE_VERSION = "4"` unchanged (1 hit), `SCHEMA_VERSION = "7"` unchanged (1 hit), `factors.py`/`VERSION` zero diff, `structural.py` diff has zero `flow_reconciliation` hits, module sizes 90/113/188 all within budget, `ruff check` clean on all touched files, caller-sweep grep matches expected file set with zero `_provisional_flow_note` production/test-monkeypatch hits remaining (3 residual hits are pre-existing docstring/comment/test-name prose, not code divergence).

## Verified present (cross-cutting invariants)

- Schema stays `"7"`; only additive `board_pe_freshness` run-level key; `_ENGINE_VERSION`/`VERSION`/`factors.py`/`forward_log.py` zero hunks in the diff; `KNOWN_NA_REASONS` zero hunks.
- Flow byte-integrity: `parse_ulist`'s f184 coercion path (`_coerce`) is untouched (only f127 half is new); AC-1 flow-identity guard test explicitly asserts f184 halves equal the pre-change parser output; `flow_reconciliation` untouched (0 grep hits in structural.py diff); top-5 slice-back in `run_flow_capture` confirmed in the literal code before `append_today`.
- New modules within budget: `industry_map_store.py` = 90 lines, `board_pe_staleness.py` = 113 lines, `industry_valuation.py` = 188 lines (≤ 207).
- Store semantics verified by passing tests: refresh-on-seen (`merge_seen` refreshes `seen_at` even when industry unchanged), ≤30-calendar-day `fresh_slice`, atomic sorted-key byte-stable writes (`record_seen` byte-stability test), corrupt/missing → `{}` with WARNING, None-industry writes nothing (file not even created).
- Board-PE: `newest_nonempty` skips literal `{}` files and unreadable files, continues scanning older; ≤3-trading-day window via `trading_day_age` against the injected/cached calendar; calendar-unavailable (`None`/empty) darkens only the `stale_fallback` branch, not `FRESH` (verified by `test_fresh_is_calendar_independent`); DARK → `industry_no_data` per-stock reason path (pre-existing `KNOWN_NA_REASONS` vocabulary, no new string).
- Golden report byte-identical: `git diff ... -- tests/monitor/golden/report.html` returns 0 lines; `test_golden_file`-covering suite (`test_report_v2_invariants.py`, `test_render_types.py`) passes.

## Drift findings

None. No unimplemented plan items, no divergent implementations, no undocumented scope creep — all 28 changed files map 1:1 to the plan's File Structure table and match the plan's literal code blocks.

### Amendment (small forced divergence, doc-only)

Task 3 Step 4's expected-output line says "Expected: 14 passed" for `tests/monitor/test_board_pe_staleness.py`. The plan's own Step 1 verbatim test code (lines 512-660 of `004-plan.md`) contains 15 `def test_...` functions, and running the suite live confirms **15 passed**. This is a doc miscount in the plan, not a code divergence — the as-built test file matches the plan's Step 1 code block byte-for-byte. Amending the plan inline to correct "14 passed" → "15 passed" for consistency with the plan's own listed test code.

Plan amendment applied: `docs/2026-07-03-monitor-v4-explainability/items/004-plan.md` line 790, "Expected: 14 passed." → "Expected: 15 passed."
