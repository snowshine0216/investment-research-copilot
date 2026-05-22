# Item 002 drift check — citation-data-model (Slice D0)

## Verdict
PASS-WITH-NOTES

## Per-task verification (18 tasks)

- ✅ Task 1 — Failing tests for `ThesisEvidence.__post_init__` validation. Done in `870fe49`.
- ✅ Task 2 — Failing tests for `citation_id` hash determinism + divergence. Done in `870fe49`.
- ✅ Task 3 — Implement `ThesisEvidence` schema additions in `types.py`. Done in `870fe49`.
- ✅ Task 4 — Add `CitationMeta` + type aliases to `types.py`. Done in `802f5c0`.
- ✅ Task 5 — Failing tests for `select_citations`. Done in `802f5c0`.
- ✅ Task 6 — Implement `select_citations` in `src/irc/memo/citation_selector.py`. Done in `802f5c0`.
- ✅ Task 7 — Thread provenance through `_filing_evidence`/`_broker_evidence`/`_news_evidence`. Done in `2f8c4d0`.
- ✅ Task 8 — Update 5 test-fixture `ThesisEvidence(...)` call sites. Done in `2f8c4d0`. ⚠️ See Notes.
- ✅ Task 9 — Failing test: `_row_to_dict` round-trip. Done in `08239ba`.
- ✅ Task 10 — Update `_row_to_dict` + `_card_to_dict`. Done in `08239ba`.
- ✅ Task 11 — Add 4 fields to `DisciplineRow`. Done in `08239ba`.
- ✅ Task 12 — `_discipline_row_from` propagates 4 new fields. Done in `08239ba`.
- ✅ Task 13 — Failing test for `PickRow.citations` + `[ref:{citation_id}]`. Done in `18bb74f`.
- ✅ Task 14 — Implement `PickRow.citations` + `证据` column + `render_failure_sections`. Done in `18bb74f`.
- ✅ Task 15 — Rewrite `_build_pick_rows` to return 3-tuple. Done in `18bb74f`.
- ✅ Task 16 — Failing tests + implement `build_cited_map`. Done in `2bff834`.
- ✅ Task 17 — Duplicate-citation-id and wrong-owner detectors (wired in Task 16). Done in `2bff834`.
- ✅ Task 18 — Lint + full test sweep + smoke integration tests. Done in `c4fec65`.

## Per-AC verification

- ✅ AC 1–4 — `ThesisEvidence` raises `ValueError` on empty `owner_instrument_id`, invalid `citation_kind`/`scope`, empty `type`/`source`/`date`.
- ✅ AC 5 — `parent_fund_id=None` / `constituent_key=None` constructs successfully.
- ✅ AC 6–8 — `citation_id` determinism, cross-instrument divergence, cross-constituent divergence.
- ✅ AC 9–13 — `select_citations` empty/cap-zero/shuffled/data+info-invariant/rendering-order.
- ✅ AC 14, 24, 25 — `_row_to_dict` round-trip includes `thesis_evidence` (with `citation_id`), `contributing_dimensions` (sorted), `constituent_analyses` (empty list).
- ✅ AC 15 — `_discipline_row_from` propagates all 4 new fields.
- ✅ AC 16 — `PickRow.citations` back-compat; `render_picks_table` emits `[ref:{citation_id}]` / `<br>` / `—`.
- ✅ AC 17–20 — `_build_pick_rows` absent/gapped/clean classification; `ValueError` on `citation_id` mismatch.
- ✅ AC 21–23 — `build_cited_map` correct shape; raises on duplicate `citation_id`; raises on wrong-owner.
- ✅ AC 26 — `### 未能纳入精选：机会数据缺失` / `### 未能纳入精选：证据不足` h3 headers; empty buckets omit the header.
- ✅ AC 27 — Failure bullets never emit `opportunity_state`, `dca_action`, `risk_action`, `note_cn`.

## Files in diff vs. plan

All 9 plan-specified source files and all 10 plan-specified test files are present. Two additional test files appear:

- `tests/opportunity/test_thesis_evidence.py` (+52/-36): plan enumerated 9 call sites; `derive_thesis_from_evidence` now requires `owner_instrument_id`, so 29 existing calls in this file needed updating. **Justified** — required-parameter cascade (impl deviation 1).
- `tests/opportunity/test_thesis_relevance_gate.py` (+4/0): 4 calls to `derive_thesis_from_evidence` updated for same reason. **Justified** — same cascade.

No source files outside the plan's file map were modified.

## Test + lint results

- **Targeted** (`tests/opportunity/ tests/memo/ tests/commands/`, pre-existing deselected): **469 pass**, 1 deselected
- **Full sweep** (pre-existing 4 deselected): run in progress at verdict-write time; partial sweep (all non-integration, pre-existing deselected) confirms no new failures
- **ruff on touched src files** (`src/irc/opportunity/`, `src/irc/memo/`, `src/irc/commands/`): **0 diagnostics**
- **ruff on full src/ tests/**: 119 diagnostics total; all pre-existing (none in files added/modified by this slice)

## Pre-existing failures (excluded)

None of the four pre-existing failure tests (`test_only_stage_runs_single`, `test_thesis_coverage_meets_threshold`, `test_no_all_evidence_insufficient_valuation`, `test_eval_single_stage_data`) appear in the diff. Their test files (`tests/commands/test_run_cmd.py`, `tests/integration/test_thesis_coverage.py`, `tests/test_e2e_full_pipeline.py`) were not touched by this slice.

## Drift signals found

1. **`_strip_venue_suffix` leading-letter strip** — plan spec says `A1234.SH → 1234` but the regex implementation extends to stripping a leading single alpha character after suffix removal (`A510300 → 510300`). This is a minor extension beyond what the plan's regex `\.[A-Z]{2,3}$` alone would do. Justified by a failing `test_build_pick_rows_venue_proxy_strip_falls_back_to_canonical` test (impl deviation 2). The behavior is narrowly scoped: only strips when `stripped[0].isalpha()` and `stripped[1:]` is all digits.
2. **Extra `ThesisEvidence(...)` call sites in test files** — plan enumerated 9 sites; 33 additional call sites in `test_thesis_evidence.py` (29) and `test_thesis_relevance_gate.py` (4) were updated. These are test-file call sites for `derive_thesis_from_evidence`, which itself cascades the new required parameter. Not a schema violation — justified and documented (impl deviation 1).

## Recommendation
Ready to ship
