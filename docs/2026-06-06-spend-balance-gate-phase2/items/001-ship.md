PR: https://github.com/snowshine0216/investment-research-copilot/pull/119
Mode: A
Branch: claude/spend-balance-gate-phase2-001
Base: autodev/spend-balance-gate-phase2-feature
Title: feat(spend): Phase 2 usage-as-data convergence — recorder + EWMA + ledger decrement (001)

## /ship workflow notes
- Base overridden to the feature branch (non-protected guardrail satisfied); never targeted main.
- Step 5 tests: touched scopes green by-file (165 passed); pre-existing baseline failures out of scope (per project_test_suite_baseline). Fixed one in-branch regression (research_cmd 3-tuple mocks, `71c04ff`).
- Steps 8+9 review → items/001-review.md (PASS-WITH-NITS); 4 blockers fixed pre-push (`6c414e2`, `c509c42`, `587dc3a`), concurrency note added (`21220a6`).
- Step 10 VERSION: intentionally NOT bumped (project convention — accumulate under CHANGELOG [Unreleased]). VERSION stays 0.9.3.
- Step 11 CHANGELOG: Phase 2 entry under [Unreleased] (`fcfb5f5`).
- Step 12 TODOS.md: no spend/Phase-2 items — no update needed.
