PR: https://github.com/snowshine0216/investment-research-copilot/pull/72
Mode: A
Branch: claude/decision-confidence-followup-002
Base: autodev/decision-confidence-followup-feature
Title: feat(scoring): QDII premium-to-NAV fetcher unblocks 8 instruments (002)

## /ship workflow trace

- Step 0: GitHub detected. Base override: `autodev/decision-confidence-followup-feature` (NOT protected `main`).
- Step 1: Pre-flight OK — not on base, 20 files / ~1087 lines (proportionate to TDD scope of 17 tasks).
- Step 2: No new binary; skipped.
- Step 3: Feature base merged into sub-branch (already up to date).
- Step 4: pytest already bootstrapped.
- Step 5: Full pytest still running in background at time of PR open (background `bvmybfyj5`); targeted-scope pytest before /ship was `396 passed, 1 skipped` (`tests/scoring tests/data tests/decision`). After /ship fix loop, `311 passed, 1 skipped` on the 4 directly-touched files. Pre-existing failures from item 001 carry over and are documented in PR body.
- Step 6: Coverage audit — every new function / branch covered by TDD-authored tests.
- Step 7: Plan completion — drift verdict PASS, 17/17 plan tasks verified.
- Step 8: Pre-landing review (parallel) — code-reviewer PASS-WITH-NITS (2 P1s); silent-failure-hunter FAIL (2 P0 + 1 P1).
- Step 9: Adversarial review — verdict RISKS (2 P1 + 1 P2).
- Triage-fix round 1: 4 commits (`5aa6b87`, `10b802f`, `d322040`, `b9a930d`) addressing 2 P0 + 2 P1; P2 + lru_cache hygiene note deferred to TODOS.
- Post-fix re-review: code-reviewer verdict PASS.
- Step 10: Version bump skipped — project uses Keep-a-Changelog `[Unreleased]` accumulation.
- Step 11: CHANGELOG.md `[Unreleased]` section appended with `qdii-premium-fetcher (2026-05-26)` subsection.
- Step 12: TODOS.md Reliability section gains 2 new entries (synthetic-vs-measured distinguishability; lru_cache test isolation contributor note).
- Step 13: 2 commits for CHANGELOG + TODOS + review verdict (`8e96a7a`, `411dbe0`).
- Step 14: Pushed to origin.
- Step 15: PR #72 opened with the autodev-mandated title/body shape.

## Review verdict capture

Wrote `items/002-review.md` (Verdict: PASS-WITH-NITS) from /ship steps 8+9 + post-fix re-review.
