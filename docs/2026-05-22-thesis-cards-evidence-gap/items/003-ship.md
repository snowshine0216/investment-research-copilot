PR: https://github.com/snowshine0216/investment-research-copilot/pull/57
Mode: A
Branch: autodev/thesis-evidence-003-active-fund-constituent-layer
Base: autodev/thesis-cards-evidence-gap
Title: feat(opportunity): active-fund constituent layer + per-stock evidence (Slice A+G) (003)

## Source
/ship invocation, 15-step workflow completed:
- Step 0: platform=GitHub, base=autodev/thesis-cards-evidence-gap (autodev override; not `main` which is protected)
- Step 1: preflight OK; large-diff warning noted (2700+ insertions, 33+ files)
- Step 2: skipped (SCOPE_NEW_BINARY=false)
- Step 3: base already up to date
- Step 4: pytest framework already detected
- Step 5: full-suite run; 7 pre-existing failures match base; 1 in-branch arch-cycle failure → /ship-blocked round 1; fixed in 57dc0b3
- Step 6: ~120 new tests added in impl; all 31 spec acceptance criteria covered
- Step 7: drift verdict PASS (items/003-drift.md)
- Steps 8+9: 3 parallel reviewers (code-reviewer + silent-failure-hunter + adversarial), 2 rounds; round 1 P0 (cycle) fixed, round 2 P0s (unwired budget/lock/state) fixed in c35267a, round 3 P1 hardening fixed in 7496e94
- Steps 10–12: skipped (sub-PR into feature branch; no version/changelog bump per autodev contract)
- Step 13: working tree clean
- Step 14: pushed
- Step 15: PR #57 created

## Pre-ship fix rounds
- Round 1 (commit 57dc0b3): relocate LookthroughTarget/LookthroughKind/ThesisEvidence/ConstituentAnalysis to fundamentals/types.py; opportunity/types.py re-exports. Breaks the fundamentals→opportunity import cycle that violated tests/evals/test_architecture.py.
- Round 2 (commit c35267a): wire preflight budget/lock/state into _build_rows (defined-but-not-called bug); close validate_cli_args default-canonical-path bypass; add Path.resolve() symlink defense; skip cache write + stamp holdings_quarter_parse_failed when source_report_quarter is empty.
- Round 3 (commit 7496e94): post-review hardening — silent stale-hash discard (per spec AC 20), holdings_quarter_parse_failed also when quarter column absent, cache_write_failed stamped in fund_level_failure_reasons (visible to item 006), budget gate credits completed_ids from state file.
