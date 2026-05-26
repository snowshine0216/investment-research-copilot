Verdict: PASS

Subagent: sonnet
Plan checklist items: 35 (9 tasks)
Verified present in diff: 35
Drift findings:
  - Task 5 Step 3 / test_rejection_log.py — consequential test update (not a plan divergence)
    Evidence: tests/opportunity/test_rejection_log.py:879-892 in diff
    The test `test_gap_to_reason_citation_gate_blocked_is_last_entry` previously asserted
    `keys[-1] == "citation_gate_blocked"`. After Task 5 appended
    `"foreign_heavy_fund_level_evidence_missing"` LAST (exactly as plan Task 5 Step 2
    requires), the prior "last entry" assertion had to change. The impl agent updated it to
    assert `keys[-1] == "foreign_heavy_fund_level_evidence_missing"` and
    `"citation_gate_blocked" in keys` — both correct and necessary. This is verified by
    reading the actual hunk lines. Classified: consequential test update, not a divergence.
    Action: accepted

Task-by-task diff evidence:

Task 1 (failing tests for rule 2.5 + helpers):
  tests/opportunity/test_policy_b.py:543-872 — all 15 new test functions present verbatim
  (test_foreign_heavy_threshold_constant_is_half, 6× test_compute_foreign_listed_share_*,
  5× test_evaluate_policy_b_rule_2_5_*, 2× precedence-guard tests,
  test_rejection_reason_code_foreign_heavy_evidence_missing_is_registered,
  test_active_fund_snapshot_fund_level_evidence_defaults_to_empty)

Task 2 (ActiveFundSnapshot.fund_level_evidence field):
  src/irc/fundamentals/types.py:206-214 — field + comment appended exactly as planned

Task 3 (FOREIGN_HEAVY_THRESHOLD constant + _compute_foreign_listed_share helper):
  src/irc/opportunity/policy_b.py:236-280 — constant, _FOREIGN_EXCHANGES frozenset,
  _compute_foreign_listed_share helper all present

Task 4 (rule 2.5 block + docstring update):
  src/irc/opportunity/policy_b.py:222-235 — docstring updated to "Six-rule precedence"
  src/irc/opportunity/policy_b.py:289-326 — rule 2.5 block inserted between rule 2 and rule 3

Task 5 (RejectionReasonCode literal + _GAP_TO_REASON entry):
  src/irc/opportunity/rejection_log.py:330-352 — new literal added; new dict entry
  appended last (after citation_gate_blocked)

Task 6 (_fetch_active_fund_level_evidence helper + _build_active_fund_snapshot plumbing +
        producer test):
  src/irc/fundamentals/snapshot.py:62-164 — helper function + both return-path changes
  tests/fundamentals/test_snapshot.py:364-444 — producer test with monkeypatches

Task 7 (snapshot_cache round-trip):
  src/irc/fundamentals/snapshot_cache.py:167-199 — _active_fund_to_dict and
  _active_fund_from_dict updated
  tests/fundamentals/test_snapshot_cache.py:454-532 — two new tests (round-trip + legacy)

Task 8 (_stamp_fund_level_evidence_from_verdict + call site):
  src/irc/commands/opportunity_cmd.py:1-57 — helper function added; call site wired
  after _stamp_audit_errors_from_verdict in the publishable branch

Task 9 (best-effort offline verification — no code changes expected):
  Not in diff; correct per plan (documentation-only acceptance when no fixture present)

Incidental diff hunks accepted:
  - docs/2026-05-26-decision-confidence-followup/MASTER-PLAN.md — item order locked,
    docs-only, no functional impact
  - docs/2026-05-26-decision-confidence-followup/PROGRESS.md — progress tracking,
    docs-only, no functional impact
