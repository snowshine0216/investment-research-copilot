PR: https://github.com/snowshine0216/investment-research-copilot/pull/98
Mode: A
Branch: claude/narrative-coverage-markdown-004
Base: autodev/narrative-coverage-markdown-feature
Title: feat(narrative): H3 display discipline for insufficient report rows (004)

## Ship workflow notes
- Base = feature branch; feature pushed before sub-branch cut (no divergence).
- VERSION NOT bumped (CHANGELOG `[Unreleased]`).
- Tests (step 5): renderer-only, narrative-isolated (risk.py/states.py/analyze.py diff empty). Blast radius = tests/narrative (149 passed/1 skip). Full suite not re-run (no logic outside narrative touched; .json unchanged so memo/opportunity unaffected).
- Review (steps 8+9): items/004-review.md — Verdict PASS-WITH-NITS after a pre-push fix round (3 item-003↔004 interaction findings fixed: a952963/ed4128b); re-review P0=none. 1 minor test-thoroughness nit.
