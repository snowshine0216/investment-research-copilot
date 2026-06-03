PR: https://github.com/snowshine0216/investment-research-copilot/pull/101
Mode: A
Branch: claude/valuation-grounding-001
Base: feat/fundamental-valuation-grounding
Title: feat(opportunity): fundamental-grounded equity valuation — Phase 1 (001)

## Ship workflow notes
- Tool: `/ship` (driven by orchestrator) with autodev/project overrides.
- Step 5 (tests): scoped suite `2 failed, 1409 passed, 19 skipped` — both failures
  (`test_build_rows_qdii_row_carries_sentinel_gap`, `test_only_stage_runs_single`) independently
  re-verified pre-existing on base. Zero in-branch failures.
- Steps 8+9 (review): captured inline → `items/001-review.md` (PASS-WITH-NITS; all P0/latent fixed pre-push).
- Step 10 (version): **VERSION NOT bumped** — project convention accumulates under CHANGELOG `[Unreleased]`.
- Step 11 (CHANGELOG): `[Unreleased]` "Added — fundamental-grounded equity valuation (Phase 1)".
- Step 12 (TODOS): added deferred P1-C (stale-cache age signal) to Reliability section.
- Review verdict file: `items/001-review.md` (PASS-WITH-NITS).
