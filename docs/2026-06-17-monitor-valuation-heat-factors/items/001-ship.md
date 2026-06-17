PR: https://github.com/snowshine0216/investment-research-copilot/pull/163
Mode: A
Branch: claude/monitor-valuation-heat-factors-001
Base: monitor-valuation-heat-wiring
Title: feat(monitor): index-path valuation + unified 5-state vocab (001)

## Ship notes
- VERSION not bumped (project convention: accumulate under CHANGELOG [Unreleased]).
- CHANGELOG [Unreleased] entry added; TODOS.md follow-up added (009225/china_internet gap).
- /ship steps 8+9 review found P0 (query-time CatalogException crash) + P1 (conn leak); both fixed
  pre-push (commit 7678c95) before the PR opened. Final review verdict: PASS (items/001-review.md).
- Scoped tests green at push: 507 passed, 10 skipped; ruff clean.
