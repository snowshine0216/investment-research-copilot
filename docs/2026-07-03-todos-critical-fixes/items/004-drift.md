Verdict: PASS

## Scope

Compared `git diff autodev/todos-critical-fixes-feature...claude/todos-critical-fixes-004` against
`docs/2026-07-03-todos-critical-fixes/items/004-plan.md` (7 tasks / 33 steps). All diff hunks read
line-by-line (not summarized); all plan code blocks compared byte-for-byte against the actual diff.

## Checklist counts

- Task 1 (`foreign_heavy_fund_level_gap` predicate): 6/6 steps implemented, verbatim.
- Task 2 (`fund_level_repair.py` module): 5/5 steps implemented, verbatim (103-line new module,
  matches plan's `Step 2.3` block character-for-character).
- Task 3 (`FetchPlan` field + 4-tuple classifier, 4 call sites): 8/8 steps implemented, verbatim.
- Task 4 (`_maybe_fund_level_evidence_repair` wiring + AC7 integration heal): 6/6 steps implemented,
  verbatim.
- Task 5 (AC8 negative lockdown test): 3/3 steps implemented, verbatim.
- Task 6 (docs: snapshot.py docstring, ADR 0003 §7, CHANGELOG, TODOS.md, CONTEXT.md verify): 8/8
  steps implemented, verbatim. CONTEXT.md diff is empty (0 changes) — confirmed correct per Step 6.6
  ("expect NO edit"; the grill-time entry already matched as-built behavior).
- Task 7 (full caller sweep + lint): sweep executed by this review (commands ran directly since no
  commit was expected for this task); all pre-existing test failures diff-scoped against base.

33/33 plan steps accounted for. 6 commits on the branch map 1:1 to Tasks 1–6 (Task 7 has no commit,
as specified — "fix-forward only if a genuine regression surfaces", none found).

## Verified invariants (explicit per the review brief)

- **Leg-wise monotone merge semantics** (`fund_level_repair.py::merge_fund_level_evidence` +
  `_merged_failure_reasons`): matches plan verbatim — fresh leg wins when produced
  (`_leg(evidence, kind) or _leg(snap.fund_level_evidence, kind)`), cached leg retained otherwise,
  failure_reasons stripped of both leg-failure strings then re-appended NAV-first iff that leg is
  absent from the **merged** (not fresh, not cached) evidence. All 9 unit tests in
  `tests/fundamentals/test_fund_level_repair.py` (4 named AC2 cases + monotonicity + ordering +
  immutability + 2 refetch-wrapper tests) present and green.
- **4 `_classify_active_fund_scores` call/unpack sites, same commit as signature change**: verified
  by grep — production caller `opportunity_cmd.py:838`, test unpacks `test_opportunity_cmd.py:675`
  and `:719`, mock `return_value=(0,0,0,0)` at the `test_build_rows_stamps_policy_b_gaps...` test —
  all four land in commit `e67e9e2e` alongside the classifier body change and the `FetchPlan` field.
  No split-commit breakage possible at any intermediate commit.
- **Cached-serve wiring merges into the POST-probe snapshot**: `_maybe_fund_level_evidence_repair(probed, root=...)` — called on `probed`, never on the pre-probe `cached`, exactly at the sole
  `else: snap_obj = probed` arm the plan identified (now replaced with the repair call). Docstring
  and inline comment both state the post-probe rationale (grill R4).
  `test_repair_heals_gapped_foreign_fund_and_writes_cache` asserts `cache_probed_at` unchanged.
- **FetchPlan budget math**: `active_fund_fund_level_repair` charged at `* per_fund_level` (=4) in
  `total_calls()`; `FetchBudgetExceeded` message includes the new field. `total_calls()` tests
  confirm 4 (repair-only) and 5 (probe+repair) — never the ~35-call `per_active` term.
- **ADR 0003 §7 correction present**: "2 additional AkShare calls... ~100" → "4 additional AkShare
  calls (1 NAV + 3 topic-specific announcement endpoints)... ~200", plus the full addendum
  paragraph block (no-backoff rationale + budget-accounting note). `snapshot.py` docstring fix
  ("Per-fund call delta = 2" → "= 4 ... `_FUND_ANN_TOPIC_FNS`") also present, matching plan verbatim.

## Findings by type

- Unimplemented: none.
- Divergent: none. Every code block in the plan (Tasks 1–4, docs edits in Task 6) matches the
  actual diff byte-for-byte, including comments, docstrings, and variable names.
- Incidental/uncovered hunks: none — the diff stat (11 files, 983 insertions / 19 deletions) maps
  exactly to the plan's declared file list; no scope creep.
- Amendments: none needed. No plan text was vague enough to require inline amendment.

## Known/accepted (pre-existing baseline failures, not regressions)

Ran the Task 7 sweep directly (`tests/opportunity/`, `tests/fundamentals/`,
`tests/commands/test_opportunity_cmd*.py`, `tests/commands/test_opportunity_recorder.py`,
`tests/narrative/`, `tests/integration/test_publishable_set_lockdown.py`). 12 failures observed on
`claude/todos-critical-fixes-004`; all 12 replayed on `autodev/todos-critical-fixes-feature` (base)
via a throwaway worktree and failed **identically** (same assertion, same message) — confirmed
pre-existing, not introduced by this diff:

- `test_opportunity_cmd.py`: `test_opportunity_command_writes_three_outputs`,
  `test_opportunity_report_json_has_summary_and_rows`,
  `test_opportunity_markdown_starts_with_chinese_sections`,
  `test_empty_available_venues_treats_all_instruments_as_compatible`,
  `test_run_opportunity_threads_plan_hash_and_snapshot_cache_to_rejections`
- `test_opportunity_cmd_acceptance.py`: `test_limit_rejected_on_canonical_output_path_via_run_opportunity`,
  `test_resumable_state_skips_completed_funds`, `test_budget_gate_credits_completed_ids`
- `test_opportunity_cmd_fund_level.py`: `test_build_rows_qdii_row_carries_sentinel_gap`
- `test_opportunity_recorder.py`: `test_opportunity_run_records_debate_tasks_samples_0_to_1`
- `test_publishable_set_lockdown.py`: `test_qdii_appears_in_rejections_with_qdii_reason`,
  `test_memo_cites_only_publishable_citation_ids`

All new item-004 tests (Tasks 1–5) pass. `ruff check` on every item-004-touched file passes clean
on both branches; the 118 whole-repo lint findings are pre-existing/unrelated (e.g.
`tests/trades/test_pipeline.py` unused import) and untouched by this diff.

## Verdict rationale

Every plan step maps to an exact, verbatim diff hunk. All 4 explicitly-named invariants hold. All
sweep failures are diff-scoped pre-existing baseline noise. No scope creep, no unimplemented steps,
no divergence requiring amendment. PASS.
