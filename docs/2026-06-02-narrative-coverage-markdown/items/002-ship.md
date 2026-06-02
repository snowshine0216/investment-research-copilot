PR: https://github.com/snowshine0216/investment-research-copilot/pull/96
Mode: A
Branch: claude/narrative-coverage-markdown-002
Base: autodev/narrative-coverage-markdown-feature
Title: feat(narrative): passive-ETF fund-level deepening in `--analyze` (002)

## Ship workflow notes
- Base = feature branch (not `main`); feature branch pushed before sub-branch cut (no divergence this time).
- VERSION NOT bumped (CHANGELOG `[Unreleased]` per convention).
- Tests (step 5): blast-radius scope (narrative+opportunity+commands+integration+evals) = 7 failed / 1090 passed; all 7 pre-existing on base (subset of the documented 8); 0 in-branch failures. Full-suite re-run skipped for efficiency (item 002 blast radius covered).
- Review (steps 8+9): items/002-review.md — Verdict PASS-WITH-NITS after a pre-push fix round (adversarial P0 refuted; layer-inversion P0 + dup + observability fixed; commits c98be90/d97b3e3); re-review P0=none. 2 cosmetic nits remain.
