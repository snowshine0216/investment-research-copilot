PR: https://github.com/snowshine0216/investment-research-copilot/pull/109
Mode: A
Branch: claude/phase-d-lookthrough-pr1-001
Base: docs/phase-d-active-lookthrough-spec
Title: feat(opportunity): Phase D active-fund look-through valuation — PR1 shadow compute (001)

## Ship notes
- Driven by `/ship` (orchestrator). Base overridden to the feature branch (not `main`).
- Step 10 VERSION bump SKIPPED per project convention (accumulate under CHANGELOG `[Unreleased]`; VERSION stays 0.9.3).
- Step 11 CHANGELOG `[Unreleased]` entry already present (impl Task 20).
- Steps 8+9 review (pr-review-toolkit:code-reviewer + silent-failure-hunter + adversarial) surfaced 2 P0 + 2 P1 + 1 note — ALL fixed pre-push (commit 524ad62). Verdict captured in `items/001-review.md` (PASS-WITH-NITS).
- Tests: change-blast-radius suite green (872 passed / 3 skipped on the re-run) except 2 documented pre-existing baseline failures (`test_fund_eval_cmd`, `test_opportunity_cmd_fund_level::...qdii_sentinel`) — confirmed identical on the untouched base; not introduced here.
