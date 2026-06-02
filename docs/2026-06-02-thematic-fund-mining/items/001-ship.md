PR: https://github.com/snowshine0216/investment-research-copilot/pull/93
Mode: A
Branch: claude/thematic-fund-mining-001
Base: autodev/thematic-fund-mining-feature
Title: feat(narrative): irc narrative thematic fund mining + prospective position_risk_level (001)

## Ship workflow notes
- Base = feature branch (non-protected; `main` not used — no protected opt-in this turn).
- Base-merge: no-op (sub-branch 0 behind feature base).
- Tests (gate): narrative suite 59 passed / 1 skipped; full suite has 8 failures, ALL pre-existing (identical on base branch) — 0 in-branch regressions. Noted in PR body.
- Version: NO bump (project convention [[project_versioning_convention]] — accumulate under CHANGELOG `[Unreleased]`, static VERSION 0.9.3). CHANGELOG `[Unreleased]` entry added.
- Steps 8+9 review: 3 P0 blockers found → fixed pre-push (items/001-ship-blocked.md) → verdict captured in items/001-review.md (PASS-WITH-NITS).
