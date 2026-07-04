PR: https://github.com/snowshine0216/investment-research-copilot/pull/203
Mode: A
Branch: claude/monitor-v4-explainability-004
Base: autodev/monitor-v4-explainability-feature
Title: feat(monitor): industry fill — batch-first f127 + cross-day map store + board-PE serve-while-stale (004)

Ship route: /ship (16-step workflow, with a step-8/9 fix round pre-push)
- Tests: tests/monitor/ 1092 passed 12 skipped; per-file commands all green; ruff clean; goldens byte-identical; flow bytes unchanged
- VERSION: not bumped (project convention); CHANGELOG entry landed with impl commit 4426eaa5
- Review (steps 8+9): items/004-review.md — Verdict: PASS-WITH-NITS after 1 fix round (P0 corrupt-cache masking + P1 NOT_REQUESTED + P2 future-seen_at all FIXED in 68606f4b, re-review RESOLVED)
- TODOS.md: 1 deferred entry (board-PE row-count floor + cold-start fallback note)
- AC-15 live spot-check: PENDING at ship time (push2 total 502 block — proxied/direct/single-secid all fail this hour). MERGE PRECONDITION — re-run in a rested window; merge does not proceed without it.
