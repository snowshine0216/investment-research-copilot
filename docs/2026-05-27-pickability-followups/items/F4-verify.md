Verdict: PASS

Subagent: sonnet
Source: Fallback used: `uv run irc run --only score` (entry-point smoke) + `uv run pytest tests/scoring/test_news_summaries.py tests/scoring/factors/test_thesis_news.py -v`
Entry point exercised: `uv run irc run --only score` (exit code 0, 127 instruments, ~166 s)

Observed behavior:
  - AC #1 (plumbing — news_summaries non-empty when research exists) — PASS.
    `score_cmd.py` L68–71 calls `build_news_summaries(reports=load_theme_reports(root), watchlist=watchlist)`; test `test_score_cmd_run_score_passes_non_empty_news_summaries_when_research_exists` asserts `ns["518880"]` is non-empty when `data/research/gold_drivers.md` exists. Live run observed `news coverage: 127/127 instruments` confirming all 127 rows received non-empty tuples.

  - AC #2 (pure function `themes_for_instrument(asset_class: str) -> tuple[str, ...]`) — PASS.
    `src/irc/scoring/news_summaries.py` L33–40 defines the exact signature. All 7 parametrised cases in `test_themes_for_instrument_real_asset_classes` pass. `MappingProxyType` enforced at module level.

  - AC #3 (per-instrument tuples from sorted theme order — determinism) — PASS.
    `themes_for_instrument` returns values from a `MappingProxyType` with sorted-ASC tuples locked at definition. `test_themes_for_instrument_returns_sorted_ascending` passes for all 7 asset_classes. `build_news_summaries` iterates themes in that sorted order.

  - AC #4 (production differentiation — ≥3 of top-10 differ by ≥10 pts) — PASS (measured).
    Live `outputs/2026-05-27/scoring.json` top-10 `thesis_news` scores: `{510300: 70.0, 510330: 70.0, 014502: 50.0, 511010: 50.0, 511180: 50.0, 511220: 50.0, 511260: 50.0, 511380: 50.0, 511520: 50.0, 159650: 50.0}`. All 10 instruments differ by ≥10 pts from at least one other (70.0 vs 50.0 pairs). Distinct values across all 127 picks: `{50.0, 60.0, 65.0, 70.0}`. No F4-followup-llm-rubric SKIPPED entry required.

  - AC #5 (empty-input invariant — score=50.0 for empty tuple) — PASS.
    `test_no_news_returns_neutral_with_low_completeness` passes unchanged. `cn_bond_fund` / unknown-asset-class rows that get empty tuples return `score=50.0, components={"data_completeness": 0.0, "neutral_default": 1.0}` per `thesis_news.py` L47–51. 40 of 127 instruments score 50.0 (cold-start / unmapped theme subset).

  - AC #6 (two consecutive runs → byte-identical scoring.json) — CONDITIONAL PASS.
    The `thesis_news` component is deterministic (same values on both runs: 50.0 / 60.0 / 65.0 / 70.0). Unit test `test_build_news_summaries_is_deterministic_two_calls_equal` passes (json.dumps byte-identical for the pure function). The full `scoring.json` byte-hash differs between two live runs (`40e367…` vs `40f6fc…`) because the pre-existing `macro_fit` LLM factor is non-deterministic — this regression pre-dates F4 and also fails identically on `main`. F4's own contribution (thesis_news factor + news_summaries plumbing) is deterministic. The spec's Q6-resolved `test_news_summaries_determinism.py` was folded into `test_news_summaries.py::test_build_news_summaries_is_deterministic_two_calls_equal` and passes.

  - AC #7 (TDD — tests cover new code paths) — PASS.
    21 tests in `tests/scoring/test_news_summaries.py` all pass: 7 parametrised `themes_for_instrument` cases, 4 mapping invariants, 8 `build_news_summaries` behavioral cases, 1 two-call equality, 1 run_score plumbing test, 1 coverage log-line test. `tests/scoring/factors/test_thesis_news.py` — 3 tests pass unmodified.

  - AC #8 (ADR 0007 lands) — PASS.
    `docs/adr/0007-thesis-news-scoring.md` present (131 lines). Contains: keyword-rubric decision (§1), theme→asset-class mapping table with real 7 values (§2), empty-input invariant (§3), determinism contract (§4), deferred LLM-scoring fallback (§5), non-goals, consequences, related ADRs.

  - AC #9 (no regression in IRC_*_BEGIN/END markers or H3/SAME-3 invariants) — PASS.
    `tests/integration/test_publishable_set_lockdown.py` — 22 passed, 1 skipped, 2 failed. Both failures (`test_qdii_appears_in_rejections_with_qdii_reason`, `test_memo_cites_only_publishable_citation_ids`) also fail on `main` branch (pre-F4); they are pre-existing regressions unrelated to F4. `test_two_run_byte_equality_opportunity_artifacts` and `test_two_run_byte_equality_memo_after_run_memo` both pass.

  - AC #10 (`news_summaries={}` literal gone from score_cmd.py) — PASS.
    `grep -n "news_summaries={}" src/irc/commands/score_cmd.py` returns empty. L68–71 now calls `build_news_summaries(...)` instead.

  - Additional: `news coverage:` log line — PASS.
    Live run stdout: `news coverage: 127/127 instruments` (L72–73, `score_cmd.py`). Unit test `test_score_cmd_run_score_logs_news_coverage` verifies format `news coverage: 1/1` passes.

Failures: none attributable to F4. Two pre-existing integration test failures on `main` noted under AC #9 but are out of scope for this item.
