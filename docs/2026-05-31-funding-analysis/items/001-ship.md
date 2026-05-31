PR: https://github.com/snowshine0216/investment-research-copilot/pull/84
Mode: A
Branch: claude/funding-analysis-001
Base: autodev/funding-analysis-feature
Title: feat(fundamentals): consensus upside + pe/pb valuation inputs (001)

## Ship summary
- /ship (16-step) driven inline by the orchestrator; base overridden to the feature branch (never main).
- Step 3 merge base: already up to date. Step 5 tests: 2485 passed / 32 skipped; 8 pre-existing failures verified identical on base (not in-branch).
- Steps 8+9 review captured → items/001-review.md (PASS-WITH-NITS; A1 NaN bug fixed pre-push, commit 12d5560).
- No VERSION bump (project convention: per-item work lands under CHANGELOG [Unreleased]).
- CHANGELOG [Unreleased] entry + TODOS reliability followup committed (docs(001)).

## Pre-existing failures (NOT this item — flagged for operator)
8 tests fail identically on `autodev/funding-analysis-feature` (and therefore on `main`):
- tests/commands/test_opportunity_cmd_fund_level.py::test_build_rows_qdii_row_carries_sentinel_gap
- tests/commands/test_run_cmd.py::test_only_stage_runs_single
- tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports
- tests/integration/test_opportunity_pipeline.py (2)
- tests/integration/test_publishable_set_lockdown.py (2)
- tests/test_e2e_full_pipeline.py::test_eval_single_stage_data
