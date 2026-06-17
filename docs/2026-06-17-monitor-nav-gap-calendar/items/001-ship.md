PR: https://github.com/snowshine0216/investment-research-copilot/pull/160
Mode: A
Branch: claude/monitor-nav-gap-calendar-001
Base: claude/affectionate-greider-e105f6
Title: feat(monitor): calendar-grounded nav_quality NAV-gap check (001)

## Ship workflow notes
- Tool: `/ship` (16-step workflow, driven by the orchestrator).
- Step 3 merge-base (`origin/claude/affectionate-greider-e105f6`): already up to date.
- Step 5 tests: 826 passed / 12 skipped / 1 failed — the 1 fail is the pre-existing `fundamentals↔data` import cycle (`tests/evals/test_architecture.py`), verified present on `origin/main`. No in-branch failures remain.
- Steps 8+9 review captured inline → items/001-review.md (`Verdict: PASS`; 3 blockers fixed pre-push: `a19dc84`, `d0e3a13`, `ff55b5e`).
- Step 10 version bump: **skipped** — project convention is to accumulate under CHANGELOG `[Unreleased]` at static VERSION (no per-PR bump).
- Step 11 CHANGELOG: new `[Unreleased]` entry added (supersedes #158 as fallback).
- Step 14 push: sub-branch + feature base pushed to origin.
