PR: https://github.com/snowshine0216/investment-research-copilot/pull/201
Mode: A
Branch: claude/monitor-v4-explainability-001
Base: autodev/monitor-v4-explainability-feature
Title: feat(monitor): caveat transparency — gate reasons, overview dedupe line, weekly eval refresh, schema 7 (001)

Ship route: /ship (16-step workflow)
- Tests: tests/monitor/ + tests/ops/ 1037 passed 12 skipped; commands per-file 19 passed; ruff clean on touched .py; bash -n clean
- VERSION: not bumped (project convention); CHANGELOG entry landed with the impl (commit e6bbf232)
- TODOS.md: 2 review nits recorded (commit fd11e05e)
- Review (steps 8+9): items/001-review.md — Verdict: PASS-WITH-NITS, 0 P0, adversarial RISKS (P1/P2 only)
- Post-merge ops carried in PR body: reinstall weekly launchd agent + one manual live eval run
