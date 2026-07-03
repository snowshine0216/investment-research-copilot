PR: https://github.com/snowshine0216/investment-research-copilot/pull/202
Mode: A
Branch: claude/monitor-v4-explainability-002
Base: autodev/monitor-v4-explainability-feature
Title: feat(monitor): macro direction chips + strength tags + mechanism clause, prompt v3 (002)

Ship route: /ship (16-step workflow, with a step-8/9 fix round pre-push)
- Tests: tests/monitor/ 1042 passed 12 skipped; per-file commands (monitor_cmd 29, trace 5) + evals runner 22; ruff clean on touched; goldens byte-unchanged
- VERSION: not bumped (project convention); CHANGELOG entry landed with impl commit 110f76cb
- Review (steps 8+9): items/002-review.md — Verdict: PASS-WITH-NITS after 1 fix round (P0+P1 observability findings FIXED pre-push in fa852a35, re-review RESOLVED; adversarial CLEAN)
- TODOS.md: nothing deferred (both findings fixed, not deferred)
