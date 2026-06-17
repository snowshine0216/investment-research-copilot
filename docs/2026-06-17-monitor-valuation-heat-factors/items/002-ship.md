PR: https://github.com/snowshine0216/investment-research-copilot/pull/164
Mode: A
Branch: claude/monitor-valuation-heat-factors-002
Base: monitor-valuation-heat-wiring
Title: feat(monitor): look-through valuation for pure active funds (002)

## Ship notes
- VERSION not bumped (project convention: CHANGELOG [Unreleased]).
- CHANGELOG [Unreleased] entry + TODOS coverage-gap entry added by impl (Task 8); TODOS
  corrupt-snapshot logging follow-up added from the ship review.
- /ship steps 8+9: 0 P0 blockers. 2 nits, both PRE-EXISTING and outside item 002's diff
  (unlogged corrupt-snapshot swallow in snapshot_cache.py; duplicate-symbol last-write-wins in
  shared fund_valuation_percentile). Review verdict: PASS-WITH-NITS (items/002-review.md).
- Scoped tests green: 519 passed, 10 skipped; opportunity look-through 78 passed; ruff clean.
