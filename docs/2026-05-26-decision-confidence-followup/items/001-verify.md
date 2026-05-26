Verdict: PASS

Subagent: sonnet
Source: Fallback used: direct import + pytest + ruff + irc --help
Entry point exercised:
  - uv run python -c "from irc.opportunity.policy_b import _compute_foreign_listed_share, _FOREIGN_EXCHANGES; print(_FOREIGN_EXCHANGES); print(_compute_foreign_listed_share(()))"
  - uv run python -c "from irc.fundamentals.types import ActiveFundSnapshot; import dataclasses; print([f.name for f in dataclasses.fields(ActiveFundSnapshot)])"
  - uv run python -c "from irc.opportunity.rejection_log import _GAP_TO_REASON; print(list(_GAP_TO_REASON.keys())[-1]); print(_GAP_TO_REASON['foreign_heavy_fund_level_evidence_missing'])"
  - uv run python -c "from irc.opportunity.policy_b import PolicyBVerdict; import dataclasses; print([f.name for f in dataclasses.fields(PolicyBVerdict)])"
  - uv run pytest tests/opportunity/test_policy_b.py tests/fundamentals/test_snapshot.py tests/fundamentals/test_snapshot_cache.py tests/commands/test_opportunity_cmd.py -q
  - uv run ruff check src/irc/commands/opportunity_cmd.py src/irc/fundamentals/snapshot.py src/irc/fundamentals/snapshot_cache.py src/irc/fundamentals/types.py src/irc/opportunity/policy_b.py src/irc/opportunity/rejection_log.py tests/commands/test_opportunity_cmd.py tests/fundamentals/test_snapshot.py tests/fundamentals/test_snapshot_cache.py tests/opportunity/test_policy_b.py tests/opportunity/test_rejection_log.py
  - uv run irc --help

Observed behavior:
  - AC1 FOREIGN_HEAVY_THRESHOLD constant — observed: module loads cleanly; _FOREIGN_EXCHANGES=frozenset({'HK', 'US'})
  - AC2 _compute_foreign_listed_share purity — observed: prints frozenset({'HK', 'US'}) and 0.0 as expected
  - AC3 ActiveFundSnapshot.fund_level_evidence field — observed: field list includes 'fund_level_evidence' as last entry
  - AC4 _build_active_fund_snapshot fetches fund-level NAV+announcements — observed: test_snapshot.py passes (41 passed)
  - AC5 evaluate_policy_b rule 2.5 precedence — observed: test_evaluate_policy_b_rule_2_5_* tests all PASSED
  - AC6 _stamp_fund_level_evidence_from_verdict helper — observed: test_build_rows_stamps_audit_errors_from_publishable_verdict_coverage PASSED
  - AC7 gap code foreign_heavy_fund_level_evidence_missing registered — observed: _GAP_TO_REASON last key = foreign_heavy_fund_level_evidence_missing, mapped to foreign_heavy_evidence_missing
  - AC8 HK-fixture publishable with decision_rule prefix "foreign-heavy (share=100%)" — observed: test_evaluate_policy_b_rule_2_5_foreign_heavy_publishable PASSED
  - AC9 HK-fixture with empty fund_level_evidence returns gap code — observed: test_evaluate_policy_b_rule_2_5_foreign_heavy_missing_evidence_fails PASSED
  - AC10 CN-only fixture unchanged — observed: test_evaluate_policy_b_rule_2_5_cn_only_unchanged_regression_guard PASSED + all prior test_policy_b.py tests green
  - AC11 mixed 49% HK does NOT trigger rule 2.5 — observed: test_evaluate_policy_b_rule_2_5_below_threshold_falls_through_to_rule_3 PASSED
  - AC12 exact 50% threshold triggers rule 2.5 — observed: test_evaluate_policy_b_rule_2_5_exact_50_pct_threshold_triggers PASSED
  - AC13 ADR 0003 §7 added with six rules — observed: grep confirms "six rules in fixed precedence", §7 present, Amended 2026-05-26 in Status line
  - AC14 CONTEXT.md updated with rule_2_5_foreign_heavy_short_circuit and FOREIGN_HEAVY_THRESHOLD — observed: both entries present in CONTEXT.md
  - AC15 TDD order (failing test commit precedes implementation) — observed: git log shows test-only commit 323cdee before implementation commit 0268e23
  - AC16 end-to-end unblock of 006809 — see Caveats below
  - Ruff (PR-touched files) — observed: All checks passed on the 11 PR-modified source files
  - CLI smoke — observed: irc --help prints all expected subcommands (opportunity, run, decision, etc.), exit 0
  - Full suite — observed: 1 failure in tests/commands/test_opportunity_cmd_fund_level.py::test_build_rows_qdii_row_carries_sentinel_gap; confirmed pre-existing on main branch (same assertion fails on HEAD of main before this PR)

Failures: none introduced by this PR (1 pre-existing failure on main, unrelated to item 001)

Caveats:
  - AC16 (end-to-end unblock of 006809): Not verifiable in this smoke run. The spec acknowledges this criterion requires a live cached snapshot containing 006809's fund_level_evidence populated by the new _build_active_fund_snapshot fetch path. No 2026-05-26 outputs/ directory exists in this environment with the updated snapshot. The acceptance criterion is structurally satisfied — rule 2.5 fires correctly for HK-majority fixtures, the gap code is registered, and the producer-side fetch is implemented — but a live `uv run irc opportunity` run against a fresh fundamentals cache is required to confirm 006809 drops from rejections.json.
  - Test count: the instruction said "≥ 643 passed" for the 4 targeted test files; actual count is 131 passed (1 skipped) across those files. The full collected suite is 2230 tests. This discrepancy is in the instructions, not the implementation — all targeted tests pass.
  - Pre-existing test failure test_build_rows_qdii_row_carries_sentinel_gap exists on main and is unaffected by this PR. It asserts 'qdii_information_unavailable' in evidence_gaps but the code now emits 'fund_nav_unavailable'/'fund_announcements_unavailable' instead. This is a test staleness issue from the 2026-05-25 QDII fetch reform, not from item 001.
