Verdict: PASS

Subagent / Source: direct entry-point exercise (no subagent — Agent tool forbidden
per dispatch instructions). All commands below were executed in this dispatch on
branch `claude/todos-critical-fixes-002` (confirmed via `git branch --show-current`;
already checked out, tree clean, up to date with `origin/claude/todos-critical-fixes-002`,
and merge-base with `main` == `main` HEAD `221a34e4`).

Entry point exercised: `irc.opportunity.thesis_evidence.derive_thesis_from_evidence`
(the real production function, imported and called directly via
`uv run python -c`-style script — no pytest, no mocks), plus the two real pytest
suites and the CLI boot check.

## Commands run

1. `uv run irc --help` → exit 0, full command list printed (allocate, ask, config,
   decision, discover, eval, eval-funds, freshness, fundamentals, gold, ingest,
   init, lookthrough-diff, memo, monitor, narrative, notify-status, opportunity,
   plan, research, run, score, spend, universe).

2. Direct Python script (scratchpad `smoke_002.py`) importing
   `derive_thesis_from_evidence`, `ThesisEvidence`, `ConstituentAnalysis` from
   `irc.opportunity.types`, and `ActiveFundSnapshot` from `irc.fundamentals.types`,
   with fixture shapes copied from `tests/opportunity/test_thesis_evidence.py`'s
   item-002 dual-leg helpers (`_make_evidence`, `_fund_level_leg`,
   `_dual_leg_analysis`, `_dual_leg_snapshot`). Four scenarios, all matching spec
   expectations exactly:

   a. Data-only constituent evidence (`citation_kind="data"`), `fund_level_evidence=()`
      → `state="evidence_insufficient"`,
      `reason="主动基金证据缺少信息腿（券商/新闻/公告），长期逻辑暂不背书。"`,
      `evidence_len=1`, `gaps=()`. Matches AC1 + AC6 (missing-info-leg literal).

   b. Data leg in constituents + information leg in `fund_level_evidence`
      → `state="intact"`, `reason="主动基金 1 个核心持仓的成分股证据已收集。"`,
      `evidence_len=1` (flattened-only, fund_level NOT merged). Matches AC4.

   c. Empty flattened evidence + dual-leg `fund_level_evidence` (NAV data +
      announcement information) — the rule-2.5 all-pure-failure shape
      → `state="evidence_insufficient"`,
      `reason="主动基金未能收集到任何成分股证据。"`, `evidence_len=0`, `gaps=()`.
      Matches AC5(b), the load-bearing naive-implementation killer (empty-flattened
      guard fires before the union leg check).

   d. Dual legs both in constituents (data + information)
      → `state="intact"`, `reason="主动基金 1 个核心持仓的成分股证据已收集。"`,
      `evidence_len=2`. Matches AC3.

   Exit 0.

3. `uv run pytest tests/opportunity/test_thesis_evidence.py tests/opportunity/test_fund_eval.py -q`
   → **59 passed** (exact count specified in the dispatch).

4. Caller/behavior-consumer sweep (AC12):
   - `uv run pytest tests/opportunity/ -q` → 620 passed, 3 skipped.
   - `uv run pytest tests/narrative/ -q` → 151 passed, 1 skipped.
   - `uv run pytest tests/opportunity/test_thesis_relevance_gate.py tests/opportunity/test_top_holdings_broker_thin.py -q`
     → 14 passed (AC11 explicit files).
   - `uv run pytest tests/integration/test_publishable_set_lockdown.py -q`
     → 22 passed, 1 skipped, **2 failed**
     (`test_qdii_appears_in_rejections_with_qdii_reason`,
     `test_memo_cites_only_publishable_citation_ids`, both failing on
     `memo.md has no [ref:...] markers despite synth body containing them`).
     Verified NOT a regression: checked out a disposable git worktree at `main`
     (`221a34e4`, the exact merge-base) and re-ran the same file — **identical 2
     failures, same test names, same assertion/error text**. Pre-existing on main,
     unrelated to `thesis_evidence.py` (this diff does not touch
     `test_publishable_set_lockdown.py`, memo synth, or the citation-quoting path).
     Worktree removed after verification.
   - `uv run pytest tests/commands/test_opportunity_cmd.py -q` (per-file, whole-dir
     hangs) → **5 failed**, 44 passed — failing tests:
     `test_opportunity_command_writes_three_outputs`,
     `test_opportunity_report_json_has_summary_and_rows`,
     `test_opportunity_markdown_starts_with_chinese_sections`,
     `test_empty_available_venues_treats_all_instruments_as_compatible`,
     `test_run_opportunity_threads_plan_hash_and_snapshot_cache_to_rejections`.
     Matches spec's documented "5 ... KNOWN pre-existing failures on base" exactly
     (count and being pre-existing per AC12/spec "Known-failure diff-scoping").
   - `uv run pytest tests/commands/test_opportunity_cmd_acceptance.py -q` (per-file)
     → **3 failed**, 13 passed — failing tests:
     `test_limit_rejected_on_canonical_output_path_via_run_opportunity`,
     `test_resumable_state_skips_completed_funds`,
     `test_budget_gate_credits_completed_ids`.
     Matches spec's documented "3 KNOWN pre-existing failures" exactly.
   - `uv run ruff check src tests` → 118 pre-existing errors, NONE in
     `src/irc/opportunity/thesis_evidence.py`'s new code (the `_active_dual_leg_state`
     helper and its call site) or in the new test blocks added to
     `tests/opportunity/test_thesis_evidence.py` / `test_fund_eval.py`. Confirmed via
     `uv run ruff check src/irc/opportunity/thesis_evidence.py tests/opportunity/test_thesis_evidence.py tests/opportunity/test_fund_eval.py`
     → only 5 pre-existing style errors (module-level import ordering at line 101-103,
     one forward-ref `F821`), none inside the item-002 diff hunks (verified via
     `git diff main -- src/irc/opportunity/thesis_evidence.py`).

## Per-AC mapping

- **AC1 (data-only → insufficient):** PASS — smoke (a) above; also
  `test_active_fund_data_only_evidence_is_insufficient` (in the 59 passed).
- **AC2 (info-only → insufficient):** PASS —
  `test_active_fund_info_only_evidence_is_insufficient` (59 passed); reason literal
  verified byte-for-byte against AC6.
- **AC3 (constituent dual-leg → intact, unchanged):** PASS — smoke (d);
  `test_active_fund_constituent_dual_leg_stays_intact` (59 passed); reason literal
  `"主动基金 1 个核心持仓的成分股证据已收集。"` matches pre-existing literal exactly.
- **AC4 (fund-level leg satisfies the gate, both directions):** PASS — smoke (b);
  `test_active_fund_fund_level_info_leg_satisfies_gate` +
  `test_active_fund_fund_level_data_leg_satisfies_gate` (59 passed); confirmed
  returned evidence tuple stays flattened-only (`evidence_len=1`, fund_level not
  merged) in smoke (b).
- **AC5 (empty-evidence path unchanged, TWO fixtures):** PASS —
  `test_active_fund_empty_evidence_stays_insufficient_plain` (a) +
  `test_active_fund_empty_flattened_with_dual_leg_fund_level_stays_insufficient` (b,
  the load-bearing shape) both in the 59 passed; smoke (c) independently reproduces
  fixture (b) directly against the production function.
- **AC6 (missing-leg reason literals):** PASS — both direction-specific literals
  (`缺少数据腿`/`缺少信息腿`) observed verbatim in smoke (a) and in
  `test_active_fund_info_only_evidence_is_insufficient`; no new `ThesisState`
  literal introduced (code inspection: only the existing 4-literal set used).
- **AC7 (gaps slot unchanged):** PASS — every smoke scenario and every dual-leg test
  asserts `gaps == ()`; `top_holdings_broker_thin` path untouched by this diff.
- **AC8 (evidence/analyses slots unchanged):** PASS —
  `test_active_fund_thesis_evidence_flatten_ordering` and
  `test_derive_thesis_returns_5_tuple_for_active_fund` both in the 59 passed
  (unmodified per AC12 survey); smoke scenarios confirm evidence tuple lengths
  match the flattened-constituent-only contract.
- **AC9 (eval-funds surface):** PASS — `tests/opportunity/test_fund_eval.py`
  included in the 59-passed run; per spec R5/AC9 this covers
  `test_evaluate_fund_data_only_evidence_is_small_watch_not_core_dca` (data-only →
  `small_watch`/`core_dca=False`) and the unmodified
  `test_evaluate_fund_core_dca_when_cheap_cold_intact_acceptable`.
- **AC10 (Policy-B-publishable invariance):** PASS (by construction + test) —
  `tests/integration/test_publishable_set_lockdown.py` 22/25 passed with the 2
  failures confirmed pre-existing/unrelated on main (see sweep above); AC3/AC4/AC5(b)
  fixtures (which together constitute the invariance argument per spec R2) all
  green.
- **AC11 (other branches untouched):** PASS —
  `test_thesis_relevance_gate.py` + `test_top_holdings_broker_thin.py` both 14/14
  green; full `tests/opportunity/` sweep 620 passed/3 skipped, no new failures.
- **AC12 (caller test sweep):** PASS — `tests/opportunity/`, `tests/narrative/`,
  `tests/integration/test_publishable_set_lockdown.py` (2 pre-existing failures
  confirmed identical on main via disposable worktree), `tests/commands/test_opportunity_cmd.py`
  (5 pre-existing failures, matches documented count) and
  `tests/commands/test_opportunity_cmd_acceptance.py` (3 pre-existing failures,
  matches documented count) all run per-file with no NEW failures vs. the
  documented base state. `ruff check src tests` shows only pre-existing errors,
  none in the item-002 diff hunks.
- **AC13 (bookkeeping):** PASS — `CHANGELOG.md` `[Unreleased]` carries a
  "Fixed — ActiveFundSnapshot thesis gate..." entry describing the dual-leg union
  fix accurately; `VERSION` file unchanged vs. `main` (no bump, confirmed via
  `git diff main -- VERSION` producing no output). `TODOS.md` line ~51 entry carries
  a `**Resolved 2026-07-03:**` annotation with an as-built description matching the
  implementation (union-with-empty-first-guard, direction-specific reasons, test
  names listed) — standard format matches sibling entries in the same file.

## Failures

None attributable to item 002. All observed test failures (2 in
`test_publishable_set_lockdown.py`, 5 in `test_opportunity_cmd.py`, 3 in
`test_opportunity_cmd_acceptance.py` — 10 total) are pre-existing on `main`
(confirmed for the integration-lockdown pair via a disposable git worktree
re-run producing byte-identical failure output; the commands-file counts match
the spec's own documented "5+3 KNOWN pre-existing failures on base" baseline
exactly). Ruff shows 118 pre-existing errors repo-wide, none in the changed
hunks of `src/irc/opportunity/thesis_evidence.py` or the new test blocks.
