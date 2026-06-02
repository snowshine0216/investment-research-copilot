PR: https://github.com/snowshine0216/investment-research-copilot/pull/95
Mode: A
Branch: claude/narrative-coverage-markdown-001
Base: autodev/narrative-coverage-markdown-feature
Title: feat(narrative): active-fund autobuild for `--analyze` + fix error string (001)

## Ship workflow notes
- Base overridden to the feature branch (not `main` — protected, no opt-in this turn).
- VERSION NOT bumped (project convention: accumulate under CHANGELOG `[Unreleased]`); CHANGELOG `[Unreleased]` updated.
- Tests (step 5): full suite 8 failed / 2732 passed / 37 skipped — all 8 failures pre-existing on base (verified by checkout); 0 in-branch failures.
- Review (steps 8+9): captured in items/001-review.md — Verdict PASS after a pre-push fix round (P0 + P1s fixed; re-review CLEAN).
