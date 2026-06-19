PR: https://github.com/snowshine0216/investment-research-copilot/pull/167
Mode: A
Branch: claude/monitor-flow-stock-drilldown-001
Base: monitor-flow-stock-drilldown
Title: feat(monitor): capital-flow factor + per-stock valuation drill-down (001)

## Ship workflow notes (autodev overrides applied)
- Step 3 (merge base): no-op — sub-branch already contains the feature tip; feature branch is current with origin/main (0 behind).
- Step 5 (tests): scoped to the feature surface (full suite ~61min / hangs per baseline) — 664 passed / 12 skipped, ruff clean on changed files. The 6 ruff errors in tests/commands/test_discover_cmd.py + test_memo_cmd_citation_gate.py are pre-existing (unrelated discover/memo files).
- Steps 8+9 (review): ran 3 parallel reviewers; found 2 P0 + 3 P1; ALL fixed pre-PR (commits f7f63f7 + 6964785); re-verified closed → [001-review.md](001-review.md) Verdict PASS-WITH-NITS.
- **Step 10 (VERSION bump): SKIPPED** — project convention (accumulate under CHANGELOG [Unreleased] at static VERSION 0.9.3; do not bump per feature). The `_ENGINE_VERSION` 1→2 in monitor_cmd.py is the eval engine tag (a different thing) and IS bumped.
- Step 11 (CHANGELOG): [Unreleased] entry already present (added in slice 4).
