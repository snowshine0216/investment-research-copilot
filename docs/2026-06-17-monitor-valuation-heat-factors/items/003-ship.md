PR: https://github.com/snowshine0216/investment-research-copilot/pull/165
Mode: A
Branch: claude/monitor-valuation-heat-factors-003
Base: monitor-valuation-heat-wiring
Title: feat(monitor): heat restriction leg (003)

## Ship notes
- VERSION not bumped (project convention: CHANGELOG [Unreleased]).
- CHANGELOG [Unreleased] heat entry added at ship (the impl didn't include a CHANGELOG step);
  AUM-Δ deferral + item-001 regression-fix noted there.
- /ship steps 8+9: 0 P0 blockers. The one substantive note (parse-layer schema-drift silence) was
  FIXED pre-push (commit ac5fba7 — edge-level column check logs drift + returns N/A). 2 P2 cosmetic
  adversarial notes (场内交易+cap=0, negative cap) — no monitor-fund impact. Review verdict:
  PASS-WITH-NITS (items/003-review.md).
- Fixes item-001 test-scope regression: tests/commands/test_monitor_cmd_eval_wiring.py 4 RED → GREEN.
- Targeted tests green: 69 passed, 2 skipped (live); monitor+commands surface green; ruff clean.
