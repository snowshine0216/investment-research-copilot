PR: https://github.com/snowshine0216/investment-research-copilot/pull/71
Mode: A
Branch: claude/decision-confidence-followup-001
Base: autodev/decision-confidence-followup-feature
Title: feat(opportunity): rule 2.5 foreign-heavy short-circuit (Policy B) (001)

## /ship workflow trace

- Step 0: GitHub detected. Base: `autodev/decision-confidence-followup-feature` (autodev override; protected `main` not used).
- Step 1: Pre-flight OK — not on base, 13 files / ~776 lines (large but proportionate to TDD scope).
- Step 2: No new binary; skipped.
- Step 3: Feature base merged into sub-branch (already up to date).
- Step 4: pytest already bootstrapped.
- Step 5: Full pytest run — 2192 passed, 30 skipped, 7 pre-existing failures (verified by running same tests on the feature base — all 7 fail there too; classified pre-existing, noted in PR body).
- Step 6: Coverage audit — every new function/branch covered by TDD-authored tests (rule 2.5 publishable + failure branches, threshold edges, precedence guards, regression guard, cache round-trip, producer).
- Step 7: Plan completion — drift verdict PASS, 35/35 plan steps verified in diff.
- Step 8: Pre-landing review (parallel) — code-reviewer found P0-1 (FetchPlan undercount) + P0-2 (dead try/except) + P1-1 (decision_rule prefix discriminator); silent-failure-hunter independently confirmed the same plus 2 more P1 dead-code findings.
- Step 9: Adversarial review — verdict RISKS, 1 additional P1 (mixed-fund stale-cache force-retry).
- Triage-fix round 1: 3 commits (`67cea2e`, `04fcf87`, `845e86b`) addressing 2 P0 + 1 P1; P2 + the architectural P1 deferred to TODOS.
- Post-fix re-review: code-reviewer verdict PASS.
- Step 10: Version bump skipped — project uses Keep-a-Changelog `[Unreleased]` accumulation; not yet ready to cut a release.
- Step 11: CHANGELOG.md `[Unreleased]` section appended with `policy-b-foreign-heavy (2026-05-26)` subsection.
- Step 12: TODOS.md Reliability section gains 3 new entries (stale-cache force-retry, `_ak_call` timeout, SH-`5` prefix).
- Step 13: 1 commit for CHANGELOG + TODOS + review verdict (`9178baa`).
- Step 14: Pushed to origin.
- Step 15: PR #71 opened with the autodev-mandated title/body shape.

## Review verdict capture

Wrote `items/001-review.md` (Verdict: PASS-WITH-NITS) from /ship steps 8+9 + post-fix re-review.
