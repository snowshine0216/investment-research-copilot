PR: https://github.com/snowshine0216/investment-research-copilot/pull/82
Mode: A
Branch: claude/pickability-followups-F6
Base: autodev/pickability-followups-feature
Title: feat(opportunity+memo): reframe filing-evidence summary to disclosure-existence anchor (F6)

Source: /ship (16-step workflow, orchestrator-driven)
Workflow notes:
- Step 5 tests (`tests/opportunity tests/memo`): 794 passed, 1 pre-existing skip. Full suite (per impl agent): 2453 passed, 9 failed (all pre-existing). No new failures.
- Step 8 code-reviewer: 0 P0, 0 P1, ship-ready.
- Step 8 silent-failure hunter: 1 P0 + 1 P1 + several notes. **P0 FIXED inline in commit `9cb6765`** — cache-transition guard in `_format_appendix_line` to also match the legacy `revenue_yoy=` substring during the cache-turnover window. P1 (sanitizer regex transition-dependency comment) accepted as note.
- Step 9 adversarial: folded into Step 8 silent-failure-hunter pass.
- Step 10 version bump: PATCH 0.9.2 → 0.9.3 (display-only reframe; no public API change).
- Step 11 CHANGELOG: new `filing-evidence-summary-reframe` entry under [Unreleased].

Final commit on branch: 4c18ec7
