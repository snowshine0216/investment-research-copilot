PR: https://github.com/snowshine0216/investment-research-copilot/pull/88
Mode: A
Branch: claude/funding-analysis-005
Base: autodev/funding-analysis-feature
Title: feat(opportunity): bull/bear debate behind --adversarial (005)

## /ship workflow notes
- Driven inline by the orchestrator.
- Step 0: base overridden to the feature branch (not protected `main`).
- Step 3 merge base: already up to date.
- Step 5 tests: 2634 passed / 36 skipped; 8 pre-existing failures identical to base — 0 new.
- Steps 8+9 review captured → items/005-review.md (PASS-WITH-NITS; silent LLM swallow + parse guard + annotation fixed pre-push, commit cb9f28b).
- Step 10: no VERSION bump (CHANGELOG [Unreleased]; VERSION stays 0.9.3).
- Step 11/12: CHANGELOG [Unreleased] entry + 3 deferred TODOS (eager import, determinism test, citation test stub) — docs(005).
- ADR 0011 (adversarial-debate-advisory-only) created in the grill phase.

## Pre-existing failures (NOT this item)
8 tests fail identically on `autodev/funding-analysis-feature` (and `main`) — see items/001-ship.md for the list.
