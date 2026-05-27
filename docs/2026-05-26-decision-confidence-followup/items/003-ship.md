PR: https://github.com/snowshine0216/investment-research-copilot/pull/73
Mode: A
Branch: claude/decision-confidence-followup-003
Base: autodev/decision-confidence-followup-feature
Title: feat(memo): mirror Decision Sheet into §5 picks table (003)

## /ship workflow trace

- Step 0: GitHub. Base override: `autodev/decision-confidence-followup-feature` (not protected `main`).
- Step 1: Pre-flight OK — 13 files / 827 lines (proportionate to 8 tasks + refactor).
- Step 2: No new binary; skipped.
- Step 3: Feature base merged into sub-branch (already up to date).
- Step 4: pytest already bootstrapped.
- Step 5: Full pytest run launched in background (bn2hlxnt3); targeted-scope pytest before /ship was 432 passed, 0 failed.
- Step 6: Coverage audit — every new function/branch covered (TDD-authored).
- Step 7: Plan completion — drift verdict PASS, 8/8 tasks verified.
- Step 8: Pre-landing review (parallel) — code-reviewer PASS-WITH-NITS (1 P1); silent-failure-hunter PASS-WITH-NITS (1 P0 + 1 P1).
- Step 9: Adversarial review — verdict CLEAN.
- Triage-fix round 1: 3 commits (`96675ab`, `36700b6`, plus DEBUG log inside `96675ab`) addressing 1 P0 + 2 P1; P2 deferred to TODOs.
- Post-fix re-review: code-reviewer flagged a pre-existing 1-line stdout-vs-stderr defect (line 37) → fixed in `7ea4b64`. Final verdict: PASS-WITH-NITS (only the P2 items remain, all pre-existing).
- Step 10: Version bump skipped — Keep-a-Changelog `[Unreleased]` accumulation pattern.
- Step 11: CHANGELOG.md `[Unreleased]` section gains `memo-picks-table-decision-mirror (2026-05-26)` subsection.
- Step 12: TODOS.md not updated for item 003 — the P2 findings are pre-existing items that other PRs should address.
- Step 13: 1 commit for CHANGELOG + review verdict (`5e2aeed`).
- Step 14: Pushed to origin.
- Step 15: PR #73 opened with the autodev-mandated title/body shape.

## Review verdict capture

Wrote `items/003-review.md` (Verdict: PASS-WITH-NITS) from /ship steps 8+9 + 2 rounds of fix + final re-review.
