PR: https://github.com/snowshine0216/investment-research-copilot/pull/85
Mode: A
Branch: claude/funding-analysis-002
Base: autodev/funding-analysis-feature
Title: feat(opportunity): fundamental valuation_state + cheap-AND-intact core_dca gate (002)

## /ship workflow notes
- Driven inline by the orchestrator (consistent PR titles across the run).
- Step 0: base detection overridden to the feature branch (would otherwise pick `main`, which is protected).
- Step 3 merge base: already up to date (sub-branch cut from the pushed feature tip).
- Step 5 tests: 2517 passed / 32 skipped; 8 pre-existing failures verified identical to base (items/001-ship.md) — not in-branch. 0 new.
- Steps 8+9 review captured → items/002-review.md (PASS-WITH-NITS; 1 latent bug fixed pre-push, commit 3ef0379).
- Step 10: no VERSION bump (project convention: per-item work lands under CHANGELOG [Unreleased]; VERSION stays 0.9.3).
- Step 11/12: CHANGELOG [Unreleased] entry + 3 deferred review nits in TODOS.md (docs(002)).

## Pre-existing failures (NOT this item — flagged for operator)
8 tests fail identically on `autodev/funding-analysis-feature` (and therefore on `main`):
- tests/commands/test_opportunity_cmd_fund_level.py::test_build_rows_qdii_row_carries_sentinel_gap
- tests/commands/test_run_cmd.py::test_only_stage_runs_single
- tests/evals/test_architecture.py::test_dag_acyclic_check_true_for_valid_imports
- tests/integration/test_opportunity_pipeline.py (2)
- tests/integration/test_publishable_set_lockdown.py (2)
- tests/test_e2e_full_pipeline.py::test_eval_single_stage_data
