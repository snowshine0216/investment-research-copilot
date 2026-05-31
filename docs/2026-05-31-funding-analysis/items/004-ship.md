PR: https://github.com/snowshine0216/investment-research-copilot/pull/86
Mode: A
Branch: claude/funding-analysis-004
Base: autodev/funding-analysis-feature
Title: feat(fundamentals): deterministic compute_ratios key-ratios surface (004)

## /ship workflow notes
- Driven inline by the orchestrator.
- Step 0: base detection overridden to the feature branch (not protected `main`).
- Step 3 merge base: already up to date.
- Step 5 tests: 2559 passed / 32 skipped; 8 pre-existing failures identical to base — 0 new.
- Steps 8+9 review captured → items/004-review.md (PASS-WITH-NITS; 3 issues fixed pre-push, commit d185648).
- Step 10: no VERSION bump (CHANGELOG [Unreleased]; VERSION stays 0.9.3).
- Step 11/12: CHANGELOG [Unreleased] entry + 2 deferred TODOS (ROE unit / section drift) — docs(004).

## Pre-existing failures (NOT this item)
8 tests fail identically on `autodev/funding-analysis-feature` (and `main`) — see items/001-ship.md for the list.
