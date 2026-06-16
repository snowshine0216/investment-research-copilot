PR: https://github.com/snowshine0216/investment-research-copilot/pull/138
Mode: A
Branch: claude/monitor-eval-m3-backtest-001
Base: claude/stupefied-swirles-a9365f
Title: feat(monitor-eval): monitor_forward M3 predictive-validity backtest (001)

## Ship notes
- Base = feature branch (non-protected) — verified before PR create. NOT main.
- VERSION NOT bumped (project convention: accumulate under CHANGELOG [Unreleased] at static VERSION 0.9.3). CHANGELOG [Unreleased] entry added.
- /ship steps 8+9 review found 1 P0 (permutation no-op) + 2 spec-completeness gaps (retro unwired, momentum stubbed) + a P1 robustness cluster. ALL fixed BEFORE the PR opened (review→fix→clean re-review). Review verdict: PASS (see items/001-review.md).
- Tests scoped to the new-feature surface (305 passed); full suite is ~61min with 24 known pre-existing failures (not run in ship). Sole failure in scope is the pre-existing DAG architecture test.
