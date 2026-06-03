PR: https://github.com/snowshine0216/investment-research-copilot/pull/97
Mode: A
Branch: claude/narrative-coverage-markdown-003
Base: autodev/narrative-coverage-markdown-feature
Title: feat(narrative): markdown report enrichment — evidence prose/citations + product drivers (003)

## Ship workflow notes
- Base = feature branch; feature pushed before sub-branch cut (no divergence).
- VERSION NOT bumped (CHANGELOG `[Unreleased]`).
- Tests (step 5): narrative-isolated change (states.py diff empty). Blast radius = tests/narrative (133 passed/1 skip) + tests/memo SAME-3 (3 passed). Full 18-min suite not re-run (renderer change is narrative-only; the 8 pre-existing failures live outside narrative).
- Review (steps 8+9): items/003-review.md — Verdict PASS after a pre-push fix round (4 substantive findings + 2 nits fixed: commits 3ca2d2a/74c9a9b/de20f34/c809105 + docstring); re-review P0=none.
