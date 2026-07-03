Verdict: PASS

## Subagent

None — smoke-test performed directly (Agent tool forbidden per task instructions).

## Source

- Branch: `claude/todos-critical-fixes-004` (confirmed via `git branch --show-current`).
- Spec: `docs/2026-07-03-todos-critical-fixes/items/004-spec.md` (grilled, 11 ACs, R1-R10).
- Touched production files: `src/irc/opportunity/policy_b.py` (`foreign_heavy_fund_level_gap`,
  ~15 lines), `src/irc/fundamentals/fund_level_repair.py` (new, 114 lines — under the
  <200-line budget), `src/irc/commands/opportunity_cmd.py` (`_maybe_fund_level_evidence_repair`,
  `FetchPlan.active_fund_fund_level_repair`, 4-tuple `_classify_active_fund_scores`),
  `src/irc/fundamentals/snapshot.py` (docstring fix, +5/-line delta).
- Note: at verification time the working tree also carried a subsequent commit
  `b3c2aebc docs(004): independent second-pass PR review — PASS-WITH-NITS`, written by a
  concurrently running pr-review agent sharing this checkout (per task instructions). It did
  not touch production or test code (docs-only) and did not conflict with this smoke test.

## Entry points exercised

1. `uv run irc --help` (CLI wiring).
2. `uv run python -c "import irc.commands.opportunity_cmd; import irc.fundamentals.fund_level_repair; import irc.opportunity.policy_b; print('imports OK')"` (import graph).
3. Direct Python exercise of the real production functions (`foreign_heavy_fund_level_gap`,
   `merge_fund_level_evidence`, `FetchPlan.total_calls`) via a scratch script, fixture shapes
   copied from `tests/opportunity/test_policy_b.py` and `tests/fundamentals/test_fund_level_repair.py`.
4. `uv run pytest tests/fundamentals/test_fund_level_repair.py tests/opportunity/test_policy_b.py -q`.
5. Targeted test ids: AC7 (`test_fund_level_evidence_repair_heals_foreign_heavy_gapped_cache`),
   AC8 negative (`test_snapshot_cache_fresh_cn_heavy_gapped_fund_level_no_repair`), AC9
   (`test_repair_refires_each_run_with_zero_writes_on_persistent_failure`), plus the two
   observability tests (`test_repair_emits_attempted_and_healed_lines_on_success`,
   `test_repair_emits_attempted_and_still_gapped_lines_when_unhealed`).
6. Full sweep per AC10: `tests/opportunity/`, `tests/fundamentals/`,
   `tests/integration/test_publishable_set_lockdown.py`,
   `tests/commands/test_opportunity_cmd.py` (per-file), `tests/commands/test_opportunity_cmd_acceptance.py`
   (per-file), `uv run ruff check` (whole repo + touched-files-only).
7. Bookkeeping inspection: `CHANGELOG.md`, `TODOS.md` line 21, `docs/adr/0003-failure-mode-policy-b.md`
   §7, `CONTEXT.md`, `VERSION` (diffed against `main` via a scratch git worktree, removed after use).

## Observed behavior per AC

- **Step 1 (CLI + imports).** `irc --help` exit 0, full command list rendered. Import-graph
  one-liner: `imports OK`, exit 0.
- **AC1 (pure gate predicate) — step 2a.** `foreign_heavy_fund_level_gap` exercised directly:
  foreign-heavy (HK 5-digit constituent, weight 0.60) + empty evidence → `True`; foreign-heavy +
  both legs (`data` + `information` `ThesisEvidence`) → `False`; CN-heavy (0.45 foreign share,
  below `FOREIGN_HEAVY_THRESHOLD=0.50`) + empty evidence → `False`; empty
  `constituent_analyses` → `False` (share 0.0 guard). All 4 assertions passed against the real
  function (not a test double).
- **AC2 (pure merge, leg-wise monotone) — step 2b.** Ran the two-run oscillation scenario from
  the spec's own motivating shape: run A (fresh NAV-only, cached empty) → merged evidence
  `['data']`, `fund_level_failure_reasons=('fund_announcements_unavailable:006809',)`. Run B
  (fresh announcements-only, cached = run A's data-only result) → merged evidence
  `['data', 'information']` (both legs survive, data-leg first per producer order),
  `fund_level_failure_reasons=()` (correctly recomputed — no leg absent, no failure strings).
  Confirmed the run-A snapshot's `fund_level_evidence` was unmutated after being fed into run B's
  merge (frozen-dataclass immutability holds).
- **AC6 (FetchPlan accounting) — step 2c.** `FetchPlan(active_fund_fund_level_repair=1, ...).total_calls()`
  → `4` (not the 35-call `per_active` term). `FetchPlan(active_fund_stale_probe_only=1,
  active_fund_fund_level_repair=1, ...).total_calls()` → `5` (probe 1 + repair 4). Both match
  the spec's locked budget-trap guard.
- **AC2/AC3 mirror tests + AC1 unit tests (step 3).**
  `pytest tests/fundamentals/test_fund_level_repair.py tests/opportunity/test_policy_b.py -q` →
  **67 passed, 1 skipped** (matches the expected ~66-67 range).
- **AC7 (end-to-end heal, step 4).** `test_fund_level_evidence_repair_heals_foreign_heavy_gapped_cache`
  PASSED in isolation.
- **AC8 (no-repair regression + new negative test, step 4).**
  `test_snapshot_cache_fresh_cn_heavy_gapped_fund_level_no_repair` PASSED in isolation. Full
  `tests/integration/test_publishable_set_lockdown.py` run: 24 passed, 1 skipped, **2 failed**
  (`test_qdii_appears_in_rejections_with_qdii_reason`, `test_memo_cites_only_publishable_citation_ids`)
  — see Failures below; both are pre-existing on `main`, confirmed by diff-scoping in a
  disposable worktree at `main` HEAD (`221a34e4`), same assertion failures reproduced verbatim.
  The four named AC8 lockdown regressions (`test_snapshot_cache_within_window_zero_akshare_calls`,
  `test_snapshot_cache_expired_probe_same_quarter_reuses`, `test_snapshot_cache_probe_failure_fail_closed_refetch`,
  and the four `_maybe_freshness_probe` unit tests) are among the 24 that passed.
- **AC9 (repeat-failure bound, step 4).**
  `test_repair_refires_each_run_with_zero_writes_on_persistent_failure` PASSED — fetch attempted
  each of two sequential calls, zero cache writes, snapshot served both times, as spec'd.
- **Observability (ship review round-1 addition).**
  `test_repair_emits_attempted_and_healed_lines_on_success` and
  `test_repair_emits_attempted_and_still_gapped_lines_when_unhealed` both PASSED.
- **AC10 (test sweep + lint, step 6).**
  - `tests/opportunity/`: 626 passed, 3 skipped.
  - `tests/fundamentals/`: 397 passed, 38 skipped.
  - `tests/integration/test_publishable_set_lockdown.py`: 24 passed, 1 skipped, 2 failed
    (pre-existing, diff-scoped — see Failures).
  - `tests/commands/test_opportunity_cmd.py` (per-file, per AC10's whole-dir-hangs note): 57
    passed, **5 failed** (`test_opportunity_command_writes_three_outputs`,
    `test_opportunity_report_json_has_summary_and_rows`,
    `test_opportunity_markdown_starts_with_chinese_sections`,
    `test_empty_available_venues_treats_all_instruments_as_compatible`,
    `test_run_opportunity_threads_plan_hash_and_snapshot_cache_to_rejections`) — all 5
    diff-scoped to `main`, identical failures reproduced.
  - `tests/commands/test_opportunity_cmd_acceptance.py`: 13 passed, **3 failed**
    (`test_limit_rejected_on_canonical_output_path_via_run_opportunity`,
    `test_resumable_state_skips_completed_funds`, `test_budget_gate_credits_completed_ids`) —
    diff-scoped to `main` via a symlinked-venv worktree, identical failures reproduced.
  - `uv run ruff check src tests`: 118 pre-existing errors repo-wide (unrelated files, e.g.
    `tests/test_e2e_plan3_full_pipeline.py`, `tests/trades/test_pipeline.py`); a scoped check
    restricted to every file item 004 touches
    (`fund_level_repair.py`, `policy_b.py`, `opportunity_cmd.py`, `snapshot.py`,
    `test_fund_level_repair.py`, `test_policy_b.py`) reports **"All checks passed!"**.
  - Total observed failing test count this session: **10** (2 + 5 + 3), **all 10 confirmed
    pre-existing on `main`** (not regressions from item 004), consistent with the spec's
    "Full pytest is NOT green on main (24 pre-existing failures)" constraint and the
    project-memory baseline note.
- **AC11 (bookkeeping + doc sync, step 5).**
  - `CHANGELOG.md` `[Unreleased]` carries a `### Fixed — fund-level evidence repair probe for
    foreign-heavy cached snapshots (2026-07-03)` entry naming the predicate, module, budget
    class, and "No VERSION bump."
  - `TODOS.md` line 21 is `[x]` with a `**Resolved 2026-07-03:**` annotation naming the
    predicate (`foreign_heavy_fund_level_gap`), the repair module
    (`src/irc/fundamentals/fund_level_repair.py`), the trigger-condition correction
    (leg-gap mirror, not `== ()`), and the specific test names/files.
  - `docs/adr/0003-failure-mode-policy-b.md` §7 "Fetch budget impact" now reads "4 additional
    AkShare calls ... adds ~200 calls" (corrected from the stale "2 ... ~100" claim), with a
    matching addendum paragraph ("Fund-level evidence repair on the cached-serve path — 2026-07-03
    addendum") covering trigger, 4-call cost, leg-wise merge, and the dedicated `FetchPlan` class.
  - `CONTEXT.md` gained the "Fund-level evidence repair (repair probe)" term (line 88) plus a
    cross-reference sentence in "Foreign-heavy fund (rule 2.5 short-circuit)" (line 114).
  - `VERSION`: `0.9.3` on both the branch and `main` — unchanged, confirmed via
    `git show main:VERSION` against the branch's working-tree `VERSION`.

## Failures

None attributable to item 004. All 10 observed test failures across the AC10 sweep
(`test_qdii_appears_in_rejections_with_qdii_reason`,
`test_memo_cites_only_publishable_citation_ids`,
`test_opportunity_command_writes_three_outputs`,
`test_opportunity_report_json_has_summary_and_rows`,
`test_opportunity_markdown_starts_with_chinese_sections`,
`test_empty_available_venues_treats_all_instruments_as_compatible`,
`test_run_opportunity_threads_plan_hash_and_snapshot_cache_to_rejections`,
`test_limit_rejected_on_canonical_output_path_via_run_opportunity`,
`test_resumable_state_skips_completed_funds`,
`test_budget_gate_credits_completed_ids`) were diff-scoped against `main` (HEAD `221a34e4`) in
disposable git worktrees and reproduce byte-identical assertion failures there — confirmed
pre-existing, not regressions introduced by this item, consistent with the project's documented
"24 pre-existing failures on main" baseline.

No AC-specific test failed. No ruff violation in item-004-touched files. VERSION untouched.
Bookkeeping (CHANGELOG, TODOS, ADR 0003 §7, CONTEXT.md) all present and consistent with the
as-built code.
