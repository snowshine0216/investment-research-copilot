PR: https://github.com/snowshine0216/investment-research-copilot/pull/87
Mode: A
Branch: claude/funding-analysis-003
Base: autodev/funding-analysis-feature
Title: feat(fundamentals): pluggable CN data layer + Tushare fallback (003)

## /ship workflow notes
- Driven inline by the orchestrator.
- Step 0: base overridden to the feature branch (not protected `main`).
- Step 2: `tushare` is a runtime dependency, not a new distributable binary → no release-pipeline action.
- Step 3 merge base: already up to date.
- Step 5 tests: 2601 passed / 34 skipped; 8 pre-existing failures identical to base — 0 new.
- Steps 8+9 review captured → items/003-review.md (PASS-WITH-NITS; 2 issues fixed pre-push, commit c9edf3a).
- Step 10: no VERSION bump (CHANGELOG [Unreleased]; VERSION stays 0.9.3).
- Step 11/12: CHANGELOG [Unreleased] entry + 3 deferred TODOS (tushare dep, column drift, failure-reason key) — docs(003). README Tushare-setup section added by the impl.
- ADR 0010 (cn-fundamentals-provider-seam) created in the grill phase.

## Pre-existing failures (NOT this item)
8 tests fail identically on `autodev/funding-analysis-feature` (and `main`) — see items/001-ship.md for the list.
